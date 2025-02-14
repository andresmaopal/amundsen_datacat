import sys
import json
import textwrap
import uuid
import os
from elasticsearch import Elasticsearch
from pyhocon import ConfigFactory
from sqlalchemy.ext.declarative import declarative_base
from databuilder.extractor.neo4j_extractor import Neo4jExtractor
from databuilder.extractor.neo4j_search_data_extractor import Neo4jSearchDataExtractor
from databuilder.extractor.postgres_metadata_extractor import PostgresMetadataExtractor
from databuilder.extractor.sql_alchemy_extractor import SQLAlchemyExtractor
from databuilder.job.job import DefaultJob
from databuilder.loader.file_system_elasticsearch_json_loader import FSElasticsearchJSONLoader
from databuilder.loader.file_system_neo4j_csv_loader import FsNeo4jCSVLoader
from databuilder.publisher import neo4j_csv_publisher
from databuilder.publisher.elasticsearch_publisher import ElasticsearchPublisher
from databuilder.publisher.neo4j_csv_publisher import Neo4jCsvPublisher
from databuilder.task.task import DefaultTask
from databuilder.transformer.base_transformer import NoopTransformer
from datetime import datetime, timedelta
from databuilder.extractor.athena_metadata_extractor import AthenaMetadataExtractor

import logging

# VARIABLE DEFINITION ------------------------

es_host = '10.0.2.23'
neo_host = '10.0.2.23'


NEO4J_ENDPOINT = f'bolt://{neo_host or "localhost"}:7687'

neo4j_endpoint = NEO4J_ENDPOINT

neo4j_user = 'neo4j'
neo4j_password = 'test'

es = Elasticsearch([
{'host': es_host if es_host else 'localhost'},
])

# todo: connection string needs to change
SUPPORTED_SCHEMAS = ['default','tpc','tpcds']
# String format - ('schema1', schema2', .... 'schemaN')
SUPPORTED_SCHEMA_SQL_IN_CLAUSE = "('{schemas}')".format(schemas="', '".join(SUPPORTED_SCHEMAS))

OPTIONAL_TABLE_NAMES = ''
AWS_ACCESS = 'XXXXX'
AWS_SECRET = 'XXXXX'

def lambda_handler(event, context):
    
    # Uncomment next line to get INFO level logging
    logging.basicConfig(level=logging.INFO)
    
    print("STARTING NEO4 job")
    
    loading_job = create_table_extract_job()

    loading_job.launch()
    print("FINISHED NEO4 job")

    print("STARTING Elasticsearch job")

    job_es_table = create_es_publisher_sample_job(
        elasticsearch_index_alias='table_search_index',
        elasticsearch_doc_type_key='table',
        model_name='databuilder.models.table_elasticsearch_document.TableESDocument')
    job_es_table.launch()
    print("FINISHED Elasticsearch job")
    
    
    return {
        'statusCode': 200,
        'body': json.dumps('Hello from Lambda!')
    }
    
    
def connection_string():
    access_key = AWS_ACCESS
    secret = AWS_SECRET
    host = 'athena.us-east-1.amazonaws.com'
    extras = 's3_staging_dir=s3://at-scale-athenaquery-east1t/'
    return "awsathena+rest://%s:%s@%s:443/?%s" % (access_key, secret, host, extras)
    
def create_table_extract_job():
    where_clause_suffix = f"where table_schema in {SUPPORTED_SCHEMA_SQL_IN_CLAUSE}"

    tmp_folder = '/tmp/amundsen/table_metadata'
    node_files_folder = f'{tmp_folder}/nodes/'
    relationship_files_folder = f'{tmp_folder}/relationships/'

    job_config = ConfigFactory.from_dict({
        f'extractor.athena_metadata.{AthenaMetadataExtractor.WHERE_CLAUSE_SUFFIX_KEY}': where_clause_suffix,
        f'extractor.athena_metadata.extractor.sqlalchemy.{SQLAlchemyExtractor.CONN_STRING}': connection_string(),
        f'extractor.athena_metadata.{AthenaMetadataExtractor.CATALOG_KEY}': "'AwsDataCatalog'",
        f'loader.filesystem_csv_neo4j.{FsNeo4jCSVLoader.NODE_DIR_PATH}': node_files_folder,
        f'loader.filesystem_csv_neo4j.{FsNeo4jCSVLoader.RELATION_DIR_PATH}': relationship_files_folder,
        f'publisher.neo4j.{neo4j_csv_publisher.NODE_FILES_DIR}': node_files_folder,
        f'publisher.neo4j.{neo4j_csv_publisher.RELATION_FILES_DIR}': relationship_files_folder,
        f'publisher.neo4j.{neo4j_csv_publisher.NEO4J_END_POINT_KEY}': neo4j_endpoint,
        f'publisher.neo4j.{neo4j_csv_publisher.NEO4J_USER}': neo4j_user,
        f'publisher.neo4j.{neo4j_csv_publisher.NEO4J_PASSWORD}': neo4j_password,
        f'publisher.neo4j.{neo4j_csv_publisher.JOB_PUBLISH_TAG}': 'unique_tag',  # should use unique tag here like {ds}
    })
    
    job = DefaultJob(conf=job_config,
                     task=DefaultTask(extractor=AthenaMetadataExtractor(), loader=FsNeo4jCSVLoader(),
                                      transformer=NoopTransformer()),
                     publisher=Neo4jCsvPublisher())

    return job
    
def create_es_publisher_sample_job(elasticsearch_index_alias='table_search_index',
                                   elasticsearch_doc_type_key='table',
                                   model_name='databuilder.models.table_elasticsearch_document.TableESDocument',
                                   cypher_query=None,
                                   elasticsearch_mapping=None):
    """
    :param elasticsearch_index_alias:  alias for Elasticsearch used in
                                       amundsensearchlibrary/search_service/config.py as an index
    :param elasticsearch_doc_type_key: name the ElasticSearch index is prepended with. Defaults to `table` resulting in
                                       `table_search_index`
    :param model_name:                 the Databuilder model class used in transporting between Extractor and Loader
    :param cypher_query:               Query handed to the `Neo4jSearchDataExtractor` class, if None is given (default)
                                       it uses the `Table` query baked into the Extractor
    :param elasticsearch_mapping:      Elasticsearch field mapping "DDL" handed to the `ElasticsearchPublisher` class,
                                       if None is given (default) it uses the `Table` query baked into the Publisher
    """
    # loader saves data to this location and publisher reads it from here
    extracted_search_data_path = '/tmp/amundsen/search_data.json'

    task = DefaultTask(loader=FSElasticsearchJSONLoader(),
                       extractor=Neo4jSearchDataExtractor(),
                       transformer=NoopTransformer())

    # elastic search client instance
    elasticsearch_client = es
    # unique name of new index in Elasticsearch
    elasticsearch_new_index_key = 'tables' + str(uuid.uuid4())

    job_config = ConfigFactory.from_dict({
        f'extractor.search_data.extractor.neo4j.{Neo4jExtractor.GRAPH_URL_CONFIG_KEY}': neo4j_endpoint,
        f'extractor.search_data.extractor.neo4j.{Neo4jExtractor.MODEL_CLASS_CONFIG_KEY}': model_name,
        f'extractor.search_data.extractor.neo4j.{Neo4jExtractor.NEO4J_AUTH_USER}': neo4j_user,
        f'extractor.search_data.extractor.neo4j.{Neo4jExtractor.NEO4J_AUTH_PW}': neo4j_password,
        f'loader.filesystem.elasticsearch.{FSElasticsearchJSONLoader.FILE_PATH_CONFIG_KEY}': extracted_search_data_path,
        f'loader.filesystem.elasticsearch.{FSElasticsearchJSONLoader.FILE_MODE_CONFIG_KEY}': 'w',
        f'publisher.elasticsearch.{ElasticsearchPublisher.FILE_PATH_CONFIG_KEY}': extracted_search_data_path,
        f'publisher.elasticsearch.{ElasticsearchPublisher.FILE_MODE_CONFIG_KEY}': 'r',
        f'publisher.elasticsearch.{ElasticsearchPublisher.ELASTICSEARCH_CLIENT_CONFIG_KEY}':
            elasticsearch_client,
        f'publisher.elasticsearch.{ElasticsearchPublisher.ELASTICSEARCH_NEW_INDEX_CONFIG_KEY}':
            elasticsearch_new_index_key,
        f'publisher.elasticsearch.{ElasticsearchPublisher.ELASTICSEARCH_DOC_TYPE_CONFIG_KEY}':
            elasticsearch_doc_type_key,
        f'publisher.elasticsearch.{ElasticsearchPublisher.ELASTICSEARCH_ALIAS_CONFIG_KEY}':
            elasticsearch_index_alias
    })

    # only optionally add these keys, so need to dynamically `put` them
    if cypher_query:
        job_config.put(f'extractor.search_data.{Neo4jSearchDataExtractor.CYPHER_QUERY_CONFIG_KEY}',
                       cypher_query)
    if elasticsearch_mapping:
        job_config.put(f'publisher.elasticsearch.{ElasticsearchPublisher.ELASTICSEARCH_MAPPING_CONFIG_KEY}',
                       elasticsearch_mapping)

    job = DefaultJob(conf=job_config,
                     task=task,
                     publisher=ElasticsearchPublisher())
    return job
