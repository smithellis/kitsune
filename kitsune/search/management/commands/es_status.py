import json
from django.core.management.base import BaseCommand
from elasticsearch import Elasticsearch
from django.conf import settings

from kitsune.search.es_utils import es_client


class Command(BaseCommand):
    help = "Check the status of the Elasticsearch connection"

    def handle(self, *args, **options):
        self.stdout.write("Checking Elasticsearch connection...")
        
        # Print connection settings
        self.stdout.write("\nConnection Settings:")
        self.stdout.write(f"ES_URLS: {settings.ES_URLS}")
        self.stdout.write(f"ES_USE_SSL: {settings.ES_USE_SSL}")
        self.stdout.write(f"ES_TIMEOUT: {settings.ES_TIMEOUT}")
        self.stdout.write(f"ES_CLOUD_ID: {bool(settings.ES_CLOUD_ID)}")
        self.stdout.write(f"ES_HTTP_AUTH: {'Configured' if settings.ES_HTTP_AUTH else 'Not Configured'}")
        
        # Try to connect and get cluster info
        try:
            client = es_client()
            info = client.info()
            
            self.stdout.write("\nConnection successful!")
            self.stdout.write(f"Elasticsearch version: {info['version']['number']}")
            self.stdout.write(f"Cluster name: {info['cluster_name']}")
            
            # Get indices info
            indices = client.indices.get_alias(index="*")
            self.stdout.write(f"\nFound {len(indices)} indices:")
            for idx in indices:
                self.stdout.write(f" - {idx}")
                
            # Check health
            health = client.cluster.health()
            self.stdout.write(f"\nCluster health: {health['status']}")
            self.stdout.write(f"Number of nodes: {health['number_of_nodes']}")
            
            return True
            
        except Exception as e:
            self.stdout.write(self.style.ERROR("\nConnection failed!"))
            self.stdout.write(self.style.ERROR(f"Error type: {type(e).__name__}"))
            self.stdout.write(self.style.ERROR(f"Error message: {str(e)}"))
            
            # Try a raw connection to help diagnose issues
            self.stdout.write("\nAttempting direct connection...")
            try:
                es_direct = Elasticsearch(
                    hosts=settings.ES_URLS,
                    verify_certs=False,
                    ssl_show_warn=False,
                    request_timeout=60,
                )
                direct_info = es_direct.info()
                self.stdout.write(self.style.SUCCESS("Direct connection successful!"))
                self.stdout.write(f"Direct version: {direct_info['version']['number']}")
            except Exception as e2:
                self.stdout.write(self.style.ERROR("Direct connection failed!"))
                self.stdout.write(self.style.ERROR(f"Error: {str(e2)}"))
            
            return False 