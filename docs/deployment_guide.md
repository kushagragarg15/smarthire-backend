# SmartHire Deployment Guide

This guide will walk you through deploying the SmartHire application using Docker and Docker Compose. You can deploy it locally or on a cloud provider of your choice.

## Prerequisites

- Docker and Docker Compose installed
- Git (to clone the repository)
- An OpenAI API key for the resume parsing functionality

## Deployment Options

### Option 1: Local Deployment with Docker Compose

1. **Clone the repository**

```bash
git clone <your-repository-url>
cd smarthire
```

2. **Set up environment variables**

Create a `.env` file in the root directory with the following variables:

```
OPENAI_API_KEY=your_openai_api_key
FLASK_ENV=production
MONGODB_URI=mongodb://mongo:27017/smarthire
```

3. **Build and start the containers**

```bash
docker-compose -f smarthire-frontend/docker-compose.yml up -d
```

4. **Access the application**

- Frontend: http://localhost:3000
- Backend API: http://localhost:5000

### Option 2: Cloud Deployment (AWS)

#### Prerequisites
- AWS account
- AWS CLI installed and configured
- Docker and Docker Compose installed

#### Steps

1. **Create an Amazon ECR repository for your images**

```bash
aws ecr create-repository --repository-name smarthire-frontend
aws ecr create-repository --repository-name smarthire-backend
```

2. **Authenticate Docker to your ECR registry**

```bash
aws ecr get-login-password --region <your-region> | docker login --username AWS --password-stdin <your-account-id>.dkr.ecr.<your-region>.amazonaws.com
```

3. **Build and tag your Docker images**

```bash
# Build and tag frontend
docker build -t <your-account-id>.dkr.ecr.<your-region>.amazonaws.com/smarthire-frontend:latest ./smarthire-frontend

# Build and tag backend
docker build -t <your-account-id>.dkr.ecr.<your-region>.amazonaws.com/smarthire-backend:latest -f Dockerfile.backend .
```

4. **Push the images to ECR**

```bash
docker push <your-account-id>.dkr.ecr.<your-region>.amazonaws.com/smarthire-frontend:latest
docker push <your-account-id>.dkr.ecr.<your-region>.amazonaws.com/smarthire-backend:latest
```

5. **Deploy using AWS ECS or AWS App Runner**

You can use AWS ECS (Elastic Container Service) or AWS App Runner to deploy your containers. Follow the AWS documentation for detailed steps.

### Option 3: Deployment on Render.com

Render.com offers a simple way to deploy Docker applications.

1. **Sign up for a Render account**

2. **Create a new Web Service**

3. **Connect your GitHub repository**

4. **Configure the service**
   - Select "Docker" as the environment
   - Set the Docker Compose file path to `smarthire-frontend/docker-compose.yml`
   - Add your environment variables (OPENAI_API_KEY, etc.)

5. **Deploy the service**

### Option 4: Deployment on Heroku

1. **Install the Heroku CLI and log in**

```bash
heroku login
```

2. **Create a Heroku app**

```bash
heroku create smarthire-app
```

3. **Add the Heroku container registry**

```bash
heroku container:login
```

4. **Build and push the Docker images**

```bash
# For the backend
heroku container:push web -a smarthire-app --context-path=. --dockerfile=Dockerfile.backend

# For the frontend (you'll need a separate Heroku app)
heroku create smarthire-frontend
heroku container:push web -a smarthire-frontend --context-path=./smarthire-frontend
```

5. **Release the containers**

```bash
heroku container:release web -a smarthire-app
heroku container:release web -a smarthire-frontend
```

6. **Set up environment variables**

```bash
heroku config:set OPENAI_API_KEY=your_openai_api_key -a smarthire-app
```

## Database Setup

The MongoDB database will be automatically set up when using Docker Compose. For cloud deployments, you may want to use a managed MongoDB service like MongoDB Atlas.

## SSL Configuration

For production deployments, you should configure SSL certificates. You can use Let's Encrypt to obtain free SSL certificates.

## Monitoring and Maintenance

- Set up monitoring using tools like Prometheus and Grafana
- Configure log aggregation using ELK stack or a service like Datadog
- Set up automated backups for your MongoDB database

## Troubleshooting

If you encounter any issues during deployment:

1. Check the container logs:
```bash
docker-compose -f smarthire-frontend/docker-compose.yml logs
```

2. Verify that all services are running:
```bash
docker-compose -f smarthire-frontend/docker-compose.yml ps
```

3. Check if the MongoDB connection is working:
```bash
docker exec -it smarthire_mongo_1 mongosh
```

4. Test the API endpoints:
```bash
curl http://localhost:5000/health
```