
FROM python:3.12-slim

WORKDIR /code

COPY ./code /code

RUN pip install --upgrade pip \
    && pip install -r /code/requirements.txt

EXPOSE 8080

CMD ["python", "/code/main.py"]
