FROM python:3.7

WORKDIR /server

COPY requirements.txt .
RUN pip3 install -r requirements.txt

COPY * ./

CMD python3 -u server.py
