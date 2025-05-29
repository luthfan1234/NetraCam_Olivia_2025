from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()

class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_superadmin(self):
        return self.role == 'super-admin'

class ActivityLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    details = db.Column(db.String(255))
    type = db.Column(db.String(50))  # 'wifi', 'gps', 'detection', 'system', etc.
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'details': self.details,
            'color': self.get_color(),
            'icon': self.get_icon(),
            'type': self.type,
            'time': self.timestamp.strftime('%H:%M:%S'),
            'date': self.timestamp.strftime('%d/%m/%Y')
        }
    
    def get_color(self):
        colors = {
            'wifi': 'blue',
            'gps': 'green',
            'detection': 'purple',
            'telegram': 'blue',
            'settings': 'yellow',
            'system': 'gray',
            'error': 'red'
        }
        return colors.get(self.type, 'gray')
        
    def get_icon(self):
        icons = {
            'wifi': 'fa-wifi',
            'gps': 'fa-location-dot',
            'detection': 'fa-eye',
            'telegram': 'fa-paper-plane',
            'settings': 'fa-gear',
            'system': 'fa-microchip',
            'error': 'fa-triangle-exclamation'
        }
        return icons.get(self.type, 'fa-circle-info')
