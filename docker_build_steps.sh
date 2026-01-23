#!/usr/bin/bash
docker-compose build
#docker-compose start
#docker-compose down
docker-compose up

#docker compose build --no-cache fastapi-app

# In case of DB update remove the postgres_data volume
docker volume rm rl-gym-harness-ui_postgres_data