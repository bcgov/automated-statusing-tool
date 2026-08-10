import redis

redis_client=redis.Redis(host='localhost', port=6379, decode_responses=True)


def get_db():
    yield redis_client

