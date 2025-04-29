"""
Management command to set up Elasticsearch indexes for testing.
"""

import logging
import re
from django.core.management.base import BaseCommand
from kitsune.search.es_utils import get_doc_types, es_client

log = logging.getLogger('kitsune.search.es.commands')


class Command(BaseCommand):
    help = 'Set up Elasticsearch indexes for testing'

    def add_arguments(self, parser):
        parser.add_argument(
            '--recreate',
            action='store_true',
            dest='recreate',
            default=False,
            help='Recreate the indexes if they already exist',
        )

    def handle(self, *args, **options):
        recreate = options['recreate']
        client = es_client()

        # Create write indexes
        for doc_type in get_doc_types():
            index_name = doc_type._index._name
            index_exists = client.indices.exists(index=index_name)

            # If recreate is True, delete existing index
            if index_exists and recreate:
                self.stdout.write(f"Deleting existing index: {index_name}")
                client.indices.delete(index=index_name)
                index_exists = False

            # Create index if it doesn't exist
            if not index_exists:
                try:
                    self.stdout.write(f"Creating index: {index_name}")
                    doc_type.init()
                    # Ensure it's ready by refreshing
                    client.indices.refresh(index=index_name)
                    self.stdout.write(self.style.SUCCESS(f"Successfully created index: {index_name}"))
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f"Error creating index {index_name}: {e}")
                    )
            else:
                self.stdout.write(f"Index {index_name} already exists, skipping.")
        
        # Create read aliases for each index
        for doc_type in get_doc_types():
            write_index = doc_type._index._name
            
            # Convert write index to read index by replacing 'write' with 'read' at the end
            if write_index.endswith('_write'):
                read_index = write_index.replace('_write', '_read')
            else:
                read_index = write_index + '_read'
            
            if not client.indices.exists(index=read_index):
                # Create an alias from read to write so they point to the same index
                try:
                    self.stdout.write(f"Creating alias from {read_index} to {write_index}")
                    client.indices.put_alias(index=write_index, name=read_index)
                    self.stdout.write(self.style.SUCCESS(f"Successfully created read alias: {read_index}"))
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f"Error creating read alias {read_index}: {e}")
                    )

        # Verify all indexes
        for doc_type in get_doc_types():
            index_name = doc_type._index._name
            if client.indices.exists(index=index_name):
                self.stdout.write(self.style.SUCCESS(f"✅ Index {index_name} is ready"))
            else:
                self.stdout.write(
                    self.style.ERROR(f"❌ Index {index_name} failed to create")
                )
                
            # Verify read alias 
            if index_name.endswith('_write'):
                read_alias = index_name.replace('_write', '_read')
            else:
                read_alias = index_name + '_read'
                
            if client.indices.exists_alias(name=read_alias):
                self.stdout.write(self.style.SUCCESS(f"✅ Read alias {read_alias} is ready"))
            else:
                self.stdout.write(
                    self.style.ERROR(f"❌ Read alias {read_alias} does not exist")
                ) 