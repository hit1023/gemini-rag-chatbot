# hello-server

アクセスすると `Hello` とだけ返す最小のDockerサーバー。

## ビルド & 起動

```bash
docker build -t hello-server .
docker run -d -p 8000:8000 --name hello-server hello-server
```

## 確認

```bash
curl http://localhost:8000/
# => Hello
```
