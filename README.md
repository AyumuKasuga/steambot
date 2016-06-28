# @StoreSteamBot

Simple bot for searching games in steam store with inline mode.

https://telegram.me/StoreSteamBot


## Docker run

https://hub.docker.com/r/ayumukasuga/steambot/ 

```
docker run --restart=always --link redis:redis --name st -d -v /home/ubuntu/steambot_conf/:/steambot/conf/ ayumukasuga/steambot
```

Place your `config.json` into conf dir (`/home/ubuntu/steambot_conf/` in this example)

Also you need redis container :)



P.S. Code is not very well, i know, but it's just prototype.