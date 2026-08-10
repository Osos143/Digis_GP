import pymongo
import redis

# 1. Test MongoDB Connection
try:
    mongo_client = pymongo.MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=2000)
    mongo_client.admin.command('ping')
    print("✅ Successfully connected to MongoDB!")
except Exception as e:
    print(f"❌ MongoDB connection failed: {e}")

# 2. Test Redis Connection
try:
    redis_client = redis.Redis(host='localhost', port=6379, db=0, socket_timeout=2)
    redis_client.ping()
    print("✅ Successfully connected to Redis!")
except Exception as e:
    print(f"❌ Redis connection failed: {e}")