import os
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, BotoCoreError
import hashlib
from io import BytesIO
import logging

from config.settings import Settings

settings = Settings()
logger = logging.getLogger(__name__)



class ObjectStorage:
    """
    S3-compatible object storage client used by AST/UOT.

    Provides environment-aware storage paths, connection validation,
    object listing, presigned URL generation, and helper methods for
    uploading geospatial outputs (GeoTIFF, GeoJSON, shapefile ZIPs)
    and reports (PDF) to an S3-compatible object store.

    Objects are organized under an application-specific storage root derived
    from the configured application directory and deployment environment
    (development, test, or production).

    Attributes:
    S3_ENDPOINT (str):
        URL of the S3-compatible storage endpoint.
    S3_ACCESS_ID (str):
        Access key ID used for authentication.
    S3_KEY (str):
        Secret access key used for authentication.
    S3_BUCKET (str):
        Target bucket used for object storage.
    S3_APP_DIR (str):
        Root application directory within the bucket.
    APP_ENVIRONMENT (str | None):
        Deployment environment. Expected values are
        'development', 'test', or 'production'.
    storage_root (str):
        Computed object prefix used as the base path for
        environment-specific storage.
    client:
        Configured boto3 S3 client instance.
    """

    ENV_FOLDER_LOOKUP = {'development':'dev','test':'test','production':'prod'}
    def __init__(self, S3_ENDPOINT, S3_ACCESS_ID, S3_KEY, S3_BUCKET, S3_APP_DIR, VERIFY=True, APP_ENVIRONEMENT=None):
        self.S3_ENDPOINT =S3_ENDPOINT
        self.S3_ACCESS_ID=S3_ACCESS_ID
        self.S3_KEY=S3_KEY
        self.S3_BUCKET=S3_BUCKET
        self.S3_APP_DIR=S3_APP_DIR
        self.APP_ENVIRONMENT = APP_ENVIRONEMENT
        self.storage_root = self.__storage_root()

        s3_config = Config(
            signature_version="s3v4",
            # request_checksum_calculation="when_required",
            # response_checksum_validation="when_required",
            retries={
                'max_attempts': 5,
                'mode': 'standard'
                }
            )

        # establish S3 connection
        self.client = boto3.client(
            's3',
            aws_access_key_id=self.S3_ACCESS_ID,
            aws_secret_access_key=self.S3_KEY,
            endpoint_url=self.S3_ENDPOINT,
            verify=VERIFY,
            config=s3_config
            )
    def __storage_root(self):
        env_folder = self.ENV_FOLDER_LOOKUP[self.APP_ENVIRONMENT]
        if self.APP_ENVIRONMENT is not None:
            base_prefix = self.S3_APP_DIR + '/' + env_folder
        else:
            base_prefix = ""
        return base_prefix
        
    def connected(self) -> bool:
        try:
            logger.debug('Checking connection to S3 Enpoint: %s', self.S3_ENDPOINT)
            if self.APP_ENVIRONMENT.lower() == 'development':
                # local dev may not have bucket created
                try:
                    logger.debug('Accessing S3 bucket head %s', self.S3_BUCKET)
                    self.client.head_bucket(Bucket=self.S3_BUCKET)
                    logger.debug('Access to S3 bucket head success')
                except ClientError:
                    logger.debug('Access S3 bucket head failed, creating bucket for %s', self.APP_ENVIRONMENT)
                    self.client.create_bucket(Bucket=self.S3_BUCKET)
                    logger.debug('Access S3 bucket head created')

            else:
                logger.debug('Accessing S3 bucket head %s', self.S3_BUCKET)
                self.client.head_bucket(Bucket=self.S3_BUCKET)
                logger.debug('Access to S3 bucket head success')
            return True

        except (BotoCoreError, ClientError) as e:
            logger.warning('Failed to connect to S3 Endpoint')
            print(f"Connection failed: {e}")
            return False
    def write_image(self, file_path: str, raster, delete: bool=False):
        raster.seek(0)
        hasher = hashlib.sha256()
        raster.seek(0)
        local_sha256 = hasher.hexdigest()

        if delete:
            pattern = file_path.split('_')[-1]
            prefix = f'{self.S3_MAIN_DIR}/{os.path.dirname(file_path)}'

            response = self.client.list_objects_v2(Bucket=self.S3_BUCKET, Prefix=prefix)
            objects = response.get('Contents', [])
            files_to_delete = [{'Key': obj['Key']} for obj in objects if pattern in obj['Key']]

            if files_to_delete:
                for i in range(0, len(files_to_delete), 1000):
                    chunk = files_to_delete[i : i + 1000]
                    self.client.delete_objects(
                        Bucket=self.S3_BUCKET, Delete={'Objects': chunk}, ChecksumAlgorithm='SHA256'
                    )

        self.client.put_object(Bucket=self.S3_BUCKET,
                                  Key=f'{self.S3_MAIN_DIR}/{file_path}',
                                  Body=raster,
                                  ContentType='image/tiff',
                                #   ChecksumAlgorithm='SHA256',
                                #   ChecksumSHA256=local_sha256
                                  )

        
    def write_shape(self, file_path: str, zip_buffer) -> bool:

        zip_buffer.seek(0)
        hasher = hashlib.sha256()
        hasher.update(zip_buffer.getvalue())
        zip_buffer.seek(0)
        local_sha256 = hasher.hexdigest()
        self.client.put_object(Bucket=self.S3_BUCKET,
                                  Key=f'{self.S3_MAIN_DIR}/{file_path}',
                                  Body=zip_buffer,
                                  ContentType='application/zip',
                                #   ChecksumAlgorithm='SHA256',
                                #   ChecksumSHA256=local_sha256
                                  )

    
    def write_json(self, file_path: str, geo_json) -> bool:

        hasher = hashlib.sha256()
        hasher.update(geo_json)
        local_sha256 = hasher.hexdigest()
        self.client.put_object(Bucket=self.S3_BUCKET,
                                  Key=f'{self.S3_MAIN_DIR}/{file_path}',
                                  Body=geo_json,
                                  ContentType='application/geo+json',
                                #   ChecksumAlgorithm='SHA256',
                                #   ChecksumSHA256=local_sha256
                                  )
    def write_pdf(self, file_path: str, pdf_buffer: BytesIO) -> bool:
        pdf_buffer.seek(0)
        hasher = hashlib.sha256()
        hasher.update(pdf_buffer.getvalue())
        pdf_buffer.seek(0)
        local_sha256 = hasher.hexdigest()

        self.client.put_object(
            Bucket=self.S3_BUCKET,
            Key=f'{self.S3_MAIN_DIR}/{file_path}',
            Body=pdf_buffer,
            ContentType='application/pdf',
            # ChecksumAlgorithm='SHA256',
            # ChecksumSHA256=local_sha256
        )
        return True
    
    def list_objects(self, file_prefix=None)->list:
        """Lists files in an S3-compliant bucket with an optional prefix."""
        if self.APP_ENVIRONMENT is not None:
            base_prefix = self.S3_APP_DIR + '/' + self.APP_ENVIRONMENT
        else:
            base_prefix = ""
        if file_prefix is not None:
            file_prefix = base_prefix + '/' + file_prefix
        else:
            file_prefix = base_prefix
        obj_list = []
        try:
            response = self.client.list_objects_v2(Bucket=self.S3_BUCKET, Prefix=f"{self.S3_MAIN_DIR}/{file_prefix}")
            if 'Contents' in response:
                logger.debug(f"Files in bucket '{self.S3_BUCKET}' (prefix: '{file_prefix}'):")
                for obj in response['Contents']:
                    # logger.info(f"- {obj['Key']} (Size: {obj['Size']} bytes)")

                    # only append file that are not directories
                    if not obj['Key'].endswith('$') and not obj['Key'].endswith('/') and not obj['Key'].endswith('catalogs'):
                        obj_list.append(obj)

            else:
                logger.warning(f"No files found in bucket '{self.S3_BUCKET}' with prefix '{file_prefix}'.")
            return obj_list
        except Exception as e:
            logger.error(f"Error listing files: {e}")
    def get_presigned_url(self, object_key, expiration_seconds=3600):

        """
            Generates a presigned URL to retrieve an S3 object.

            :param object_key: The S3 object key (path to the file).
            :param expiration_seconds: The number of seconds the URL is valid for.
            :return: The presigned URL, or None if an error occurs.
            """
        try:
            response = self.client.generate_presigned_url(
                ClientMethod='get_object',
                Params={'Bucket': self.S3_BUCKET, 'Key': object_key},
                ExpiresIn=expiration_seconds
            )
            return response
        except ClientError as e:
            logger.error(f"ClientError generating presigned URL for {object_key}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error generating presigned URL for {object_key}: {e}")
            return None

def app_object_storage(settings=Settings())->ObjectStorage:
    return ObjectStorage(S3_ENDPOINT=settings.results_s3_endpoint_url,
                         S3_ACCESS_ID=settings.results_s3_access_id,
                         S3_BUCKET=settings.results_s3_bucket,
                         S3_APP_DIR=settings.main_directory,
                         S3_KEY=settings.results_s3_key,
                         VERIFY=settings.s3_use_ssl)

    