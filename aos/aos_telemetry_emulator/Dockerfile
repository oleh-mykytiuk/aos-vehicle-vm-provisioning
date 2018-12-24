FROM python:3.6-alpine

LABEL maintainer="Oleh Mykytiuk <oleh_mykytiuk@epam.com>"

ENV PYTHONUNBUFFERED 1
ENV PYTHONDONTWRITEBYTECODE 1

COPY map.json /app/aos_telemetry_emulator/
COPY *.py /app/aos_telemetry_emulator/

WORKDIR /app/aos_telemetry_emulator/

CMD ["python", "emulator_rest.py"]

EXPOSE 80
