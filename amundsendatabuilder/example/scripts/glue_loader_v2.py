import textwrap
import logging
import os

from elasticsearch import Elasticsearch
from sqlalchemy.ext.declarative import declarative_base
from pyhocon import ConfigFactory

from databuilder.extractor.glue_extractor import GlueExtractor
from databuilder.job.job import DefaultJob
from databuilder.task.task import DefaultTask
from databuilder.transformer.base_transformer import NoopTransformer
from databuilder.publisher import neo4j_csv_publisher
from databuilder.loader.file_system_neo4j_csv_loader import FsNeo4jCSVLoader
from databuilder.publisher.neo4j_csv_publisher import Neo4jCsvPublisher

es_host = os.getenv('CREDENTIALS_ELASTICSEARCH_PROXY_HOST', 'localhost')
neo_host = os.getenv('CREDENTIALS_NEO4J_PROXY_HOST', 'localhost')

es_port = os.getenv('CREDENTIALS_ELASTICSEARCH_PROXY_PORT', 9200)
neo_port = os.getenv('CREDENTIALS_NEO4J_PROXY_PORT', 7687)

es = Elasticsearch([
    {'host': es_host if es_host else '0.0.0.0'}
])

Base = declarative_base()

NEO4J_ENDPOINT = 'bolt://{}:7687'.format(neo_host if neo_host else '0.0.0.0')

neo4j_endpoint = NEO4J_ENDPOINT

neo4j_user = 'neo4j'
neo4j_password = 'test'

LOGGER = logging.getLogger(__name__)

def create_extract_job():
    tmp_folder = '/var/tmp/amundsen/table_metadata'
    node_files_folder = '{tmp_folder}/nodes/'.format(tmp_folder=tmp_folder)
    relationship_files_folder = '{tmp_folder}/relationships/'.format(tmp_folder=tmp_folder)

    job_config = ConfigFactory.from_dict({
        f'extractor.glue_data.{GlueExtractor.CLUSTER_KEY}': 'FwoGZXIvYXdzEL///////////wEaDAPz9Oc3Y8dD1vXF8CKCAfAeY9+YhIEjVaR4xRwAtYDfKInh0RaJSep+O5VBstj0eraXvW8XI5I65ps0+udj7u9iZOMmulqMgOrQlaRZRkJgRbdWnjjBZiwT0nEbIuHaM7AwvJNuaOS05kG8TR+cLj+lk9zm31tgaY60Oh2dkhB9x4acgwSVEy3nSj9KzZOMTXgovMiPgQYyKN8N87xaDQQks7hkvfZ+vxF0NoNTDI2PT1sTPG7PRkk1REyQH38+2z0=',
        f'loader.filesystem_csv_neo4j.{FsNeo4jCSVLoader.NODE_DIR_PATH}': node_files_folder,
        f'loader.filesystem_csv_neo4j.{FsNeo4jCSVLoader.RELATION_DIR_PATH}': relationship_files_folder,
        f'loader.filesystem_csv_neo4j.{FsNeo4jCSVLoader.SHOULD_DELETE_CREATED_DIR}': False,
        f'loader.filesystem_csv_neo4j.{FsNeo4jCSVLoader.FORCE_CREATE_DIR}': True,
        f'publisher.neo4j.{neo4j_csv_publisher.NODE_FILES_DIR}': node_files_folder,
        f'publisher.neo4j.{neo4j_csv_publisher.RELATION_FILES_DIR}': relationship_files_folder,
        f'publisher.neo4j.{neo4j_csv_publisher.NEO4J_END_POINT_KEY}': neo4j_endpoint,
        f'publisher.neo4j.{neo4j_csv_publisher.NEO4J_USER}': neo4j_user,
        f'publisher.neo4j.{neo4j_csv_publisher.NEO4J_PASSWORD}': neo4j_password,
        f'publisher.neo4j.{neo4j_csv_publisher.JOB_PUBLISH_TAG}': 'unique_tag',  # should use unique tag here like {ds}
    })
    job = DefaultJob(
        conf=job_config,
        task= DefaultTask(
            extractor=GlueExtractor(),
            loader=FsNeo4jCSVLoader
        ),
        publisher=Neo4jCsvPublisher
    )
    job.launch()


if __name__ == "__main__":
    # Uncomment next line to get INFO level logging
    logging.basicConfig(level=logging.DEBUG)
    create_extract_job()
