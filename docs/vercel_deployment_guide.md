# Deploying SmartHire on Vercel

This guide will walk you through deploying the SmartHire application on Vercel. Since Vercel is primarily designed for frontend applications, we'll deploy the React frontend on Vercel and the backend on another platform.

## Overview

1. Deploy the frontend on Vercel
2. Deploy the backend on a platform like Render, Railway, or Heroku
3. Configure the frontend to connect to the backend API

## Step 1: Prepare the Frontend for Vercel

First, we need to make some adjustments to the frontend code to ensure it works well with Vercel.

### 1.1 Create a Vercel Configuration File

Create a `vercel.json` file in the `smarthire-frontend` directory:

```json
{
  "version": 2,
  "builds": [
    {
      "src": "package.json",
      "use": "@vercel/static-build",
      "config": { "distDir": "build" }
    }
  ],
  "routes": [
    {
      "src": "/static/(.*)",
      "dest": "/static/$1"
    },
    {
      "src": "/favicon.ico",
      "dest": "/favicon.ico"
    },
    {
      "src": "/manifest.json",
      "dest": "/manifest.json"
    },
    {
      "src": "/logo(.*)",
      "dest": "/logo$1"
    },
    {
      "src": "/(.*)",
      "dest": "/index.html"
    }
  ]
}
```

### 1.2 Update API Endpoint Configuration

Create a `.env.production` file in the `smarthire-frontend` directory to configure the production API URL:

```
REACT_APP_API_URL=https://your-backend-api-url.com
```

Replace `https://your-backend-api-url.com` with the URL where your backend will be deployed.

### 1.3 Update API Calls in the Frontend

Ensure all API calls in the frontend use the environment variable:

```javascript
// Example API call
const response = await axios.get(`${process.env.REACT_APP_API_URL || 'http://localhost:5000'}/api/endpoint`);
```

## Step 2: Deploy the Backend

Since Vercel is primarily for frontend applications, we'll deploy the backend on another platform. Here are some good options:

### Option 1: Deploy on Render.com

1. Sign up for a [Render](https://render.com) account
2. Create a new Web Service
3. Connect your GitHub repository
4. Configure the service:
   - Environment: Docker
   - Build Command: `docker build -t smarthire-backend -f Dockerfile.backend .`
   - Start Command: `docker run -p 5000:5000 smarthire-backend`
   - Add environment variables (OPENAI_API_KEY, etc.)

### Option 2: Deploy on Railway

1. Sign up for a [Railway](https://railway.app) account
2. Create a new project
3. Add a service from GitHub repository
4. Configure the service:
   - Select the Dockerfile.backend
   - Add environment variables (OPENAI_API_KEY, etc.)
   - Deploy

### Option 3: Deploy on Heroku

1. Sign up for a [Heroku](https://heroku.com) account
2. Install the Heroku CLI and log in
3. Create a new Heroku app:
   ```bash
   heroku create smarthire-backend
   ```
4. Add the Heroku container registry:
   ```bash
   heroku container:login
   ```
5. Build and push the Docker image:
   ```bash
   heroku container:push web -a smarthire-backend --dockerfile=Dockerfile.backend
   ```
6. Release the container:
   ```bash
   heroku container:release web -a smarthire-backend
   ```
7. Set up environment variables:
   ```bash
   heroku config:set OPENAI_API_KEY=your_openai_api_key -a smarthire-backend
   ```

## Step 3: Deploy the Frontend on Vercel

Now that the backend is deployed, let's deploy the frontend on Vercel:

1. Sign up for a [Vercel](https://vercel.com) account

2. Install the Vercel CLI:
   ```bash
   npm install -g vercel
   ```

3. Log in to Vercel:
   ```bash
   vercel login
   ```

4. Navigate to the frontend directory:
   ```bash
   cd smarthire-frontend
   ```

5. Deploy to Vercel:
   ```bash
   vercel
   ```

6. Follow the prompts:
   - Set up and deploy: Yes
   - Link to existing project: No
   - Project name: smarthire
   - Directory: ./
   - Override settings: No

7. Once deployed, you'll get a URL for your frontend application.

8. For subsequent deployments, use:
   ```bash
   vercel --prod
   ```

## Step 4: Configure Environment Variables on Vercel

1. Go to the Vercel dashboard
2. Select your project
3. Go to Settings > Environment Variables
4. Add the following environment variable:
   - Name: `REACT_APP_API_URL`
   - Value: Your backend API URL (e.g., `https://smarthire-backend.onrender.com`)
5. Save and redeploy if necessary

## Step 5: Configure CORS on the Backend

To allow your Vercel-hosted frontend to communicate with your backend, you need to configure CORS:

1. Update your Flask app to allow requests from your Vercel domain:

```python
from flask_cors import CORS

# Add your Vercel domain to the allowed origins
allowed_origins = [
    "https://smarthire.vercel.app",  # Replace with your actual Vercel domain
    "http://localhost:3000"  # For local development
]

# Configure CORS
CORS(app, resources={r"/*": {"origins": allowed_origins}})
```

2. Redeploy your backend with these changes

## Step 6: Test the Deployment

1. Visit your Vercel frontend URL
2. Test all functionality to ensure it's working correctly
3. Check that API calls to the backend are successful

## Troubleshooting

### CORS Issues

If you encounter CORS errors:

1. Check that your backend CORS configuration includes your Vercel domain
2. Verify that all API calls use the correct URL format
3. Check the browser console for specific error messages

### API Connection Issues

If the frontend can't connect to the backend:

1. Verify that the `REACT_APP_API_URL` is set correctly in Vercel
2. Check that your backend is running and accessible
3. Test the API endpoints directly using a tool like Postman

### Build Issues

If the build fails on Vercel:

1. Check the build logs for specific errors
2. Verify that all dependencies are correctly listed in package.json
3. Make sure the project structure is compatible with Vercel's build process

## Monitoring and Maintenance

1. Set up monitoring for both your frontend and backend
2. Configure alerts for any downtime or errors
3. Regularly check the logs for any issues
4. Keep dependencies updated to ensure security and performance

## Next Steps

1. Set up a custom domain for your Vercel deployment
2. Configure SSL for secure connections
3. Set up CI/CD for automated deployments
4. Implement monitoring and analytics