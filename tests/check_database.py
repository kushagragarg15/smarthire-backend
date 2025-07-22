#!/usr/bin/env python3
"""
Database Check Script
Shows the current state of the MongoDB database
"""

from pymongo import MongoClient
from datetime import datetime

def check_database():
    """Check and display current database state"""
    try:
        # Connect to MongoDB
        client = MongoClient("mongodb://localhost:27017/")
        db = client["smarthire"]
        resumes = db["resumes"]
        
        print("📊 SmartHire Database Status")
        print("=" * 35)
        
        # Get total count
        total_count = resumes.count_documents({})
        print(f"Total candidates: {total_count}")
        
        if total_count == 0:
            print("Database is empty.")
            return
        
        # Show all candidates
        print(f"\n👥 Current Candidates:")
        print("-" * 50)
        
        for i, doc in enumerate(resumes.find(), 1):
            print(f"\n{i}. {doc.get('name', 'No name')}")
            print(f"   Email: {doc.get('email', 'No email')}")
            
            if doc.get('phone'):
                print(f"   Phone: {doc['phone']}")
            
            if doc.get('location'):
                print(f"   Location: {doc['location']}")
            
            if doc.get('experience'):
                print(f"   Experience: {doc['experience']}")
            
            skills = doc.get('skills', [])
            if skills:
                print(f"   Skills: {', '.join(skills[:5])}{'...' if len(skills) > 5 else ''}")
            
            education = doc.get('education', [])
            if education:
                print(f"   Education: {', '.join(education[:2])}{'...' if len(education) > 2 else ''}")
            
            if doc.get('created_at'):
                created = doc['created_at']
                if isinstance(created, datetime):
                    print(f"   Added: {created.strftime('%Y-%m-%d %H:%M:%S')}")
                else:
                    print(f"   Added: {created}")
        
        # Show database stats
        print(f"\n📈 Database Statistics:")
        print("-" * 25)
        
        # Count by location
        pipeline = [
            {"$group": {"_id": "$location", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        
        location_stats = list(resumes.aggregate(pipeline))
        if location_stats:
            print("   By Location:")
            for stat in location_stats[:5]:  # Top 5 locations
                location = stat["_id"] if stat["_id"] else "Unknown"
                print(f"     {location}: {stat['count']} candidates")
        
        # Count total skills
        all_skills = []
        for doc in resumes.find({}, {"skills": 1}):
            all_skills.extend(doc.get("skills", []))
        
        if all_skills:
            skill_counts = {}
            for skill in all_skills:
                skill_counts[skill] = skill_counts.get(skill, 0) + 1
            
            top_skills = sorted(skill_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            print(f"   Top Skills:")
            for skill, count in top_skills:
                print(f"     {skill}: {count} candidates")
        
        # Check for any validation issues
        print(f"\n🔍 Validation Check:")
        print("-" * 20)
        
        issues_found = 0
        
        for doc in resumes.find():
            # Check required fields
            required_fields = ["name", "email", "skills", "education"]
            for field in required_fields:
                if field not in doc or not doc[field]:
                    print(f"   ⚠️  {doc.get('name', 'Unknown')}: Missing {field}")
                    issues_found += 1
                    break
            
            # Check email format
            email = doc.get("email", "")
            if email and "@" not in email:
                print(f"   ⚠️  {doc.get('name', 'Unknown')}: Invalid email format")
                issues_found += 1
        
        if issues_found == 0:
            print("   ✅ All candidates have valid data")
        else:
            print(f"   ⚠️  Found {issues_found} validation issues")
        
        client.close()
        
    except Exception as e:
        print(f"❌ Error checking database: {e}")

if __name__ == "__main__":
    check_database() 