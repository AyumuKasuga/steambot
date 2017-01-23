FROM ubuntu:16.10

MAINTAINER AyumuKasuga

RUN locale-gen en_US.UTF-8

ENV LANG en_US.UTF-8
ENV LC_CTYPE en_US.UTF-8
ENV LC_ALL en_US.UTF-8

ENV TZ=Europe/Moscow

RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

RUN apt-get update && apt-get upgrade -y && apt-get install python3 python3-venv -y

RUN mkdir /steambot

WORKDIR /steambot

COPY *.py /steambot/
COPY requirements.txt /steambot/

RUN /usr/bin/python3 -m venv /steambot/.venv
RUN chmod +x /steambot/.venv/bin/activate
RUN cd /steambot && /steambot/.venv/bin/pip install pip --upgrade && /steambot/.venv/bin/pip install -r requirements.txt

CMD /steambot/.venv/bin/python -u bot.py