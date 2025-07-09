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

class ProfessionalForm(FlaskForm):
    name = StringField('Nome Completo', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    role = SelectField('Função', choices=[
        ('professional', 'Fisioterapeuta'),
        ('secretary', 'Secretária(o)')
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

class ElectronicRecordForm(FlaskForm):
    medical_diagnosis = TextAreaField('Diagnóstico Médico (opcional)', validators=[Optional()])
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
    files = MultipleFileField('Exames Complementares (Fotos, Documentos)')
    diagnosis = TextAreaField('Diagnóstico Fisioterapêutico', validators=[Optional()])
    goals = TextAreaField('Objetivos (Curto, Médio e Longo Prazo)', validators=[Optional()])
    treatment_plan = TextAreaField('Plano de Tratamento', validators=[Optional()])
    submit = SubmitField('Salvar Avaliação')


