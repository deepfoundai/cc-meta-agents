import json
import boto3
from botocore.exceptions import ClientError


class SecretsManager:
    def __init__(self, region_name='us-east-1'):
        self.client = boto3.client('secretsmanager', region_name=region_name)
        self._cache = {}
    
    def get_secret(self, secret_name):
        if secret_name in self._cache:
            return self._cache[secret_name]
        
        try:
            response = self.client.get_secret_value(SecretId=secret_name)
            secret_string = response['SecretString']
            secret_dict = json.loads(secret_string)
            self._cache[secret_name] = secret_dict
            return secret_dict
        except ClientError as e:
            raise Exception(f"Error retrieving secret {secret_name}: {str(e)}")
    
    def get_openai_api_key(self):
        secret = self.get_secret('meta-agents/openai')
        return secret.get('api_key')
    
    def get_fal_api_key(self, environment='dev'):
        secret_name = f'/contentcraft/{environment}/fal/api_key'
        secret = self.get_secret(secret_name)
        return secret.get('api_key')


secrets_manager = SecretsManager()