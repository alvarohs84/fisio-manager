# forms.py

from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField, DateField, TimeField, SelectField, IntegerField, TextAreaField
from wtforms.validators import DataRequired, Email, EqualTo, ValidationError, Optional
from models import User

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Senha', validators=[DataRequired()])
    remember_me = BooleanField('Lembrar-me')
    submit = SubmitField('Entrar')

class RegistrationForm(FlaskForm):
    name = StringField('Nome Completo', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Senha', validators=[DataRequired()])
    password2 = PasswordField('Repita a Senha', validators=[DataRequired(), EqualTo('password', message='As senhas devem ser iguais.')])
    submit = SubmitField('Registrar')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user is not None:
            raise ValidationError('Este email já está cadastrado.')

class PatientForm(FlaskForm):
    full_name = StringField('Nome Completo', validators=[DataRequired()])
    date_of_birth = DateField('Data de Nascimento', format='%Y-%m-%d', validators=[DataRequired()])
    phone = StringField('Telefone', validators=[DataRequired()])
    submit = SubmitField('Salvar Paciente')

class AppointmentForm(FlaskForm):
    patient_id = SelectField('Paciente', coerce=int, validators=[DataRequired()])
    date = DateField('Data', format='%Y-%m-%d', validators=[DataRequired()])
    time = TimeField('Hora', format='%H:%M', validators=[DataRequired()])
    location = StringField('Local', validators=[DataRequired()], default='Clínica')
    notes = TextAreaField('Anotações Rápidas (opcional)', validators=[Optional()])
    
    is_recurring = BooleanField('Atendimento Recorrente?')
    frequency = IntegerField('Repetir por quantas semanas?', default=4, validators=[Optional()])
    
    submit = SubmitField('Agendar')

class UpdateAppointmentStatusForm(FlaskForm):
    status = SelectField('Alterar Status', choices=[
        ('Agendado', 'Agendado'),
        ('Concluído', 'Concluído'),
        ('Cancelado', 'Cancelado')
    ], validators=[DataRequired()])
    submit = SubmitField('Atualizar')

class ElectronicRecordForm(FlaskForm):
    subjective_notes = TextAreaField('Subjetivo (relato do paciente)', validators=[DataRequired()])
    objective_notes = TextAreaField('Objetivo (sua avaliação)', validators=[DataRequired()])
    assessment = TextAreaField('Diagnóstico Fisioterapêutico', validators=[DataRequired()])
    plan = TextAreaField('Plano de Tratamento', validators=[DataRequired()])
    submit = SubmitField('Salvar Registro no Prontuário')

class AssessmentForm(FlaskForm):
    main_complaint = TextAreaField('Queixa Principal (QP)', validators=[Optional()])
    history_of_present_illness = TextAreaField('História da Doença Atual (HDA)', validators=[Optional()])
    past_medical_history = TextAreaField('História Patológica Pregressa (HPP)', validators=[Optional()])
    medications = TextAreaField('Medicamentos em Uso', validators=[Optional()])
    social_history = TextAreaField('História Social e Hábitos de Vida', validators=[Optional()])
    
    inspection_notes = TextAreaField('Inspeção', validators=[Optional()])
    palpation_notes = TextAreaField('Palpação', validators=[Optional()])
    mobility_assessment = TextAreaField('Avaliação da Mobilidade (ADM, Goniometria, etc.)', validators=[Optional()])
    strength_assessment = TextAreaField('Avaliação da Força Muscular (Escala de Kendall, etc.)', validators=[Optional()])
    neuro_assessment = TextAreaField('Avaliação Neurológica', validators=[Optional()])
    functional_assessment = TextAreaField('Avaliação Funcional e Testes Específicos', validators=[Optional()])

    diagnosis = TextAreaField('Diagnóstico Fisioterapêutico', validators=[Optional()])
    goals = TextAreaField('Objetivos (Curto, Médio e Longo Prazo)', validators=[Optional()])
    treatment_plan = TextAreaField('Plano de Tratamento', validators=[Optional()])

    submit = SubmitField('Salvar Avaliação')