FROM python:3.7

RUN apt-get update && apt-get install -y \
        apt-transport-https \
        ca-certificates \
        curl \
        software-properties-common

RUN curl -fsSL https://download.docker.com/linux/debian/gpg | apt-key add -
RUN add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/debian $(lsb_release -cs) stable"
RUN apt-get update && apt-get install -y docker-ce

WORKDIR /dispatcher

COPY requirements.txt .
RUN pip3 install -r requirements.txt

COPY * ./

CMD python3 -u server.py
