# forms.py (versão corrigida e completa)

from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField, DateField, TimeField, SelectField, IntegerField, TextAreaField, MultipleFileField, RadioField
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

# CORREÇÃO: Renomeado de ProfessionalForm para StaffForm para corresponder à importação em app.py
class StaffForm(FlaskForm):
    name = StringField('Nome Completo', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    role = SelectField('Função', choices=[
        ('professional', 'Fisioterapeuta'),
        ('secretary', 'Secretária(o)'),
        ('admin', 'Administrador') # Adicionada a role admin para consistência
    ], validators=[DataRequired()])
    date_of_birth = DateField('Data de Nascimento', format='%Y-%m-%d', validators=[Optional()])
    cpf = StringField('CPF', validators=[Optional()])
    address = StringField('Endereço', validators=[Optional()])
    phone = StringField('Telefone', validators=[Optional()])
    crefito = StringField('CREFITO', validators=[Optional()])
    password = PasswordField('Senha (deixe em branco para não alterar)', validators=[Optional()])
    submit = SubmitField('Salvar Profissional')

class PatientForm(FlaskForm):
    full_name = StringField('Nome Completo', validators=[DataRequired()])
    date_of_birth = DateField('Data de Nascimento', format='%Y-%m-%d', validators=[DataRequired()])
    gender = RadioField('Gênero', choices=[('Feminino','Feminino'), ('Masculino','Masculino')], validators=[Optional()])
    phone = StringField('Telefone', validators=[DataRequired()])
    specialty = SelectField('Especialidade Principal',
        choices=[
            ('', '-- Selecione uma Especialidade --'),
            ('Acupuntura', 'Acupuntura'),
            ('Aquática', 'Aquática'),
            ('Cardiovascular', 'Cardiovascular'),
            ('Dermatofuncional', 'Dermatofuncional'),
            ('Esportiva', 'Esportiva'),
            ('Gerontologia', 'Gerontologia'),
            ('Trabalho', 'Saúde do Trabalhador'),
            ('Neurofuncional', 'Neurofuncional'),
            ('Oncologia', 'Oncologia'),
            ('Reumatologia', 'Reumatologia'),
            ('Respiratória', 'Respiratória/Reabilitação Pulmonar'),
            ('Traumato-Ortopédica', 'Traumato-Ortopédica'),
            ('Osteopatia', 'Osteopatia'),
            ('Quiropraxia', 'Quiropraxia'),
            ('Saúde da Mulher', 'Saúde da Mulher'),
            ('Pilates', 'Pilates')
        ],
        validators=[Optional()]
    )
    submit = SubmitField('Salvar Paciente')

# ADICIONADO: Classe ElectronicRecordForm que estava faltando
class ElectronicRecordForm(FlaskForm):
    medical_diagnosis = TextAreaField('Diagnóstico Médico', validators=[Optional()])
    subjective_notes = TextAreaField('Notas Subjetivas (S)', validators=[DataRequired()])
    objective_notes = TextAreaField('Notas Objetivas (O)', validators=[DataRequired()])
    assessment = TextAreaField('Avaliação (A)', validators=[DataRequired()])
    plan = TextAreaField('Plano (P)', validators=[DataRequired()])
    submit = SubmitField('Salvar Registro')

# ADICIONADO: Classe AssessmentForm que estava faltando
class AssessmentForm(FlaskForm):
    main_complaint = TextAreaField('Queixa Principal')
    history_of_present_illness = TextAreaField('História da Doença Atual (HDA)')
    past_medical_history = TextAreaField('História Médica Pregressa')
    medications = TextAreaField('Medicamentos em Uso')
    social_history = TextAreaField('História Social')
    inspection_notes = TextAreaField('Inspeção')
    palpation_notes = TextAreaField('Palpação')
    mobility_assessment = TextAreaField('Avaliação da Mobilidade')
    strength_assessment = TextAreaField('Avaliação da Força Muscular')
    neuro_assessment = TextAreaField('Avaliação Neurológica')
    functional_assessment = TextAreaField('Avaliação Funcional')
    diagnosis = TextAreaField('Diagnóstico Fisioterapêutico')
    goals = TextAreaField('Objetivos (Curto, Médio e Longo Prazo)')
    treatment_plan = TextAreaField('Plano de Tratamento')
    files = MultipleFileField('Anexar Ficheiros (Exames, Imagens, etc.)', validators=[Optional()])
    submit = SubmitField('Salvar Avaliação')


