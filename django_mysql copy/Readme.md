

## commands:コマンド入力


### 1. clone this repo

本リポジトリのソースコードをダウンロードします。

```sh
git clone https://github.com/kawadasatoshi/PythonImages.git
```


### 2. move to "django_mysql" directory

djangoディレクトリにcdコマンドで移動します。

```sh
cd PythonImages/django_mysql/
```


### 3. Djangoプロジェクトファイルを作ろう（move to "django" and create projectfile）

- djangoディレクトリに移動

```sh
cd django
```

- djangoイメージファイルをビルド

```sh
docker image build -t django .
```

- djangoを起動してコンテナ内部に入る

```sh
# for mac or linux user
docker run -it -p 80:80 -v ./code:/code django bash
```

```sh
# for windows user
docker run -it -p 80:80 -v ${PWD}/code:/code django bash
```

- コンテナ内部では以下のコマンドを実行

```sh
django-admin startproject mysite
python mysite/manage.py startapp myapp
python mysite/manage.py migrate
```

**ファイルが作成されればプロジェクトファイルの作成は完了**

`exit`コマンドでコンテナを抜け、`docker-compose.yml`があるディレクトリまで`cd ..`で戻る。



### 3. docker-composeでbuildする

```sh
docker-compose build
```


### 4. docker-compose upで起動

```sh
docker-compose up
```

### 5. localhostにアクセスして動作確認

http://localhost/

上記のリンクから動作が確認できれば完了


