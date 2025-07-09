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


