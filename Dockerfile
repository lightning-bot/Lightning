FROM python:3.7

WORKDIR /app

COPY requirements.txt ./

ENV JISHAKU_NO_UNDERSCORE=true

RUN pip install -e .

COPY . .

CMD [ "python", "-m", "lightning"]