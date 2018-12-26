FROM ubuntu:16.04

LABEL maintainer="Oleh Mykytiuk <oleh_mykytiuk@epam.com>"

RUN apt update && apt upgrade -y
RUN apt install -y ca-certificates

COPY cert/rootCA.pem /etc/ssl/certs/rootCA.pem

WORKDIR /app/

COPY . /app/
COPY data/ /app/data/

CMD ["./aos_vis"]

EXPOSE 443
