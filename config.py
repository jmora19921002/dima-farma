import os
from datetime import timedelta

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    # Configuración de Base de Datos vía Variables de Entorno
    DB_USER = os.environ.get('DB_USER') or 'root'
    DB_PASSWORD = os.environ.get('DB_PASSWORD') or ''
    DB_HOST = os.environ.get('DB_HOST') or 'localhost'
    DB_PORT = os.environ.get('DB_PORT') or '3306'
    DB_NAME = os.environ.get('DB_NAME') or 'dimafarm'
    DB_SSL_MODE = os.environ.get('DB_SSL_MODE') or 'REQUIRED'

    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # SSL configuration for PyMySQL
    if 'mysql+pymysql' in SQLALCHEMY_DATABASE_URI:
        SQLALCHEMY_ENGINE_OPTIONS = {
            "connect_args": {
                "ssl": {}
            }
        }
    else:
        SQLALCHEMY_ENGINE_OPTIONS = {}
    
    # JWT settings
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or 'jwt-secret-key'
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
        
    # File upload settings
    UPLOAD_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'static', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    
    # Pagination
    POSTS_PER_PAGE = 20
    
    # Subscription settings
    SUBSCRIPTION_PRICE = 99.99  # Monthly subscription price in USD
    
    # Email settings (for future use)
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
