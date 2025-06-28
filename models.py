# models.py

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date, datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    """Modelo para o Profissional (Usuário do sistema)"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), index=True, unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    
    patients = db.relationship('Patient', backref='professional', lazy='dynamic', cascade="all, delete-orphan")
    appointments = db.relationship('Appointment', backref='professional', lazy='dynamic', cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.name}>'

class Patient(db.Model):
    """Modelo para o Paciente"""
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(150), nullable=False, index=True)
    date_of_birth = db.Column(db.Date, nullable=False)
    phone = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    appointments = db.relationship('Appointment', backref='patient', lazy='dynamic', cascade="all, delete-orphan")
    records = db.relationship('ElectronicRecord', backref='patient', lazy='dynamic', cascade="all, delete-orphan")
    assessments = db.relationship('Assessment', backref='patient', lazy='dynamic', cascade="all, delete-orphan")

    @property
    def age(self):
        today = date.today()
        return today.year - self.date_of_birth.year - ((today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day))

    def __repr__(self):
        return f'<Patient {self.full_name}>'

class Appointment(db.Model):
    """Modelo para o Agendamento"""
    id = db.Column(db.Integer, primary_key=True)
    start_time = db.Column(db.DateTime, nullable=False)
    location = db.Column(db.String(150), nullable=False)
    status = db.Column(db.String(30), default='Agendado')
    notes = db.Column(db.Text, nullable=True)

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey('patient.id'), nullable=False)

    is_recurring = db.Column(db.Boolean, default=False)
    recurrence_id = db.Column(db.String(36))

    def __repr__(self):
        return f'<Appointment for {self.patient.full_name} at {self.start_time}>'

class ElectronicRecord(db.Model):
    """Modelo para cada registro no Prontuário Eletrônico"""
    id = db.Column(db.Integer, primary_key=True)
    record_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    medical_diagnosis = db.Column(db.Text, nullable=True) # Diagnóstico Médico (opcional)

    subjective_notes = db.Column(db.Text, nullable=False)
    objective_notes = db.Column(db.Text, nullable=False)
    assessment = db.Column(db.Text, nullable=False)
    plan = db.Column(db.Text, nullable=False)

    patient_id = db.Column(db.Integer, db.ForeignKey('patient.id'), nullable=False)
    
    def __repr__(self):
        return f'<Record for {self.patient.full_name} on {self.record_date}>'

class Assessment(db.Model):
    """Modelo para a Avaliação Fisioterapêutica completa."""
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    patient_id = db.Column(db.Integer, db.ForeignKey('patient.id'), nullable=False)

    main_complaint = db.Column(db.Text, nullable=True)
    history_of_present_illness = db.Column(db.Text, nullable=True)
    past_medical_history = db.Column(db.Text, nullable=True)
    medications = db.Column(db.Text, nullable=True)
    social_history = db.Column(db.Text, nullable=True)
    
    inspection_notes = db.Column(db.Text, nullable=True)
    palpation_notes = db.Column(db.Text, nullable=True)
    mobility_assessment = db.Column(db.Text, nullable=True)
    strength_assessment = db.Column(db.Text, nullable=True)
    neuro_assessment = db.Column(db.Text, nullable=True)
    functional_assessment = db.Column(db.Text, nullable=True)

    files = db.relationship('UploadedFile', backref='assessment', lazy='dynamic', cascade="all, delete-orphan")

    diagnosis = db.Column(db.Text, nullable=True)
    goals = db.Column(db.Text, nullable=True)
    treatment_plan = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f'<Assessment for {self.patient.full_name} on {self.created_at}>'

class UploadedFile(db.Model):
    """Modelo para cada ficheiro enviado."""
    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(255), nullable=False)
    secure_url = db.Column(db.String(512), nullable=False)
    resource_type = db.Column(db.String(50), nullable=False)
    
    assessment_id = db.Column(db.Integer, db.ForeignKey('assessment.id'), nullable=False)

    def __repr__(self):
        return f'<File {self.public_id}>'