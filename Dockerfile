# Use imagem base oficial do Python
FROM python:3.11-slim

# Define o diretório de trabalho
WORKDIR /app

# Copia os arquivos do projeto para o contêiner
COPY . .

# Instala as dependências
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Define o ponto de entrada
CMD ["python", "bot.py"]

