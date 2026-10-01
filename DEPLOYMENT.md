# SmartHire Deployment Guide

This guide covers deployment options for the SmartHire application.

## 🚀 Quick Deploy Options

### Option 1: Local Development
```bash
# Backend
./start.sh
# or on Windows
scripts\start_backend.bat

# Frontend (in another terminal)
cd smarthire-frontend
npm install
npm start
```

### Option 2: Production Deployment

#### Backend Deployment (Heroku/Railway/Render)

1. **Prepare for deployment:**
   ```bash
   # Ensure all dependencies are in requirements.txt
   pip freeze > requirements.txt
   ```

2. **Set environment variables:**
   ```
   OPENAI_API_KEY=your_openai_api_key
   MONGODB_URI=your_mongodb_connection_string (optional)
   FLASK_ENV=production
   ```

3. **Create Procfile for Heroku:**
   ```
   web: python main.py
   ```

#### Frontend Deployment (Vercel/Netlify)

1. **Build the frontend:**
   ```bash
   cd smarthire-frontend
   npm run build
   ```

2. **Set environment variables:**
   ```
   REACT_APP_API_URL=https://your-backend-url.com
   ```

3. **Deploy the `build` folder**

## 🔧 Environment Configuration

### Backend (.env)
```env
OPENAI_API_KEY=sk-your-openai-key-here
MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/smarthire
FLASK_ENV=production
```

### Frontend (.env)
```env
REACT_APP_API_URL=https://your-backend-domain.com
```

## 📊 Database Options

### Option 1: MongoDB (Recommended)
- Set up MongoDB Atlas (free tier available)
- Update `MONGODB_URI` in environment variables
- Automatic scaling and backup

### Option 2: JSON File Storage (Development)
- No setup required
- Files stored in `data/` directory
- Good for testing and development

## 🔒 Security Checklist

- [ ] OpenAI API key is set in environment variables
- [ ] MongoDB connection string is secure
- [ ] CORS origins are configured for production domains
- [ ] File upload limits are appropriate
- [ ] Logs don't contain sensitive information

## 🚀 Platform-Specific Guides

### Heroku Deployment
```bash
# Install Heroku CLI
heroku create your-app-name
heroku config:set OPENAI_API_KEY=your-key
heroku config:set MONGODB_URI=your-mongodb-uri
git push heroku main
```

### Vercel Frontend Deployment
```bash
# Install Vercel CLI
npm i -g vercel
cd smarthire-frontend
vercel --prod
```

### Railway Backend Deployment
1. Connect your GitHub repository
2. Set environment variables in Railway dashboard
3. Deploy automatically on push

## 🔍 Troubleshooting

### Common Issues:
1. **OpenAI API errors**: Check API key and billing
2. **MongoDB connection**: Verify connection string and network access
3. **CORS errors**: Update allowed origins in backend
4. **File upload issues**: Check file size limits and permissions

### Logs:
- Backend logs: `logs/smarthire.log`
- Frontend logs: Browser developer console
- Production logs: Check your hosting platform's log viewer