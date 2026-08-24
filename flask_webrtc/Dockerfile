
# python version number:3.9.16
FROM python:3.9.16

# code ... directory for python codes.
WORKDIR /code

# copy localcode to container image.
COPY ./code /code

# upgrade pip command
RUN pip install --upgrade pip 

# install python lib 
RUN pip install -r requirements.txt

# uvicornで起動するように変更 (app.pyのappインスタンスを指定)
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "80"]