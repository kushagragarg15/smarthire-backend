#!/usr/bin/env python3
"""
Test script to verify the job matching functionality
"""

import requests
import json
from pprint import pprint

def test_job_matching():
    """Test the job matching functionality"""
    
    print("🧪 Testing Job Matching Functionality")
    print("=" * 50)
    
    # Test the resume_matches endpoint
    try:
        response = requests.get("http://localhost:5000/resume_matches", timeout=10)
        response.raise_for_status()
        data = response.json()
        
        print(f"✅ Successfully connected to resume_matches endpoint")
        
        if isinstance(data, list):
            print(f"📊 Found {len(data)} candidates with resume data")
            
            # Check if candidates have matches
            for i, candidate_data in enumerate(data[:3], 1):  # Show first 3 candidates
                candidate = candidate_data.get('candidate', {})
                matches = candidate_data.get('matches', [])
                
                print(f"\n👤 Candidate {i}: {candidate.get('name', 'Unknown')}")
                print(f"📧 Email: {candidate.get('email', 'No email')}")
                print(f"🔍 Match count: {len(matches)}")
                
                if matches:
                    print(f"🏆 Top matches:")
                    for j, match in enumerate(matches[:3], 1):  # Show top 3 matches
                        score = match.get('scores', {}).get('final', 0) * 100
                        print(f"  {j}. {match.get('title', 'Unknown job')} - {score:.1f}% match")
                        
                        # Show score breakdown
                        scores = match.get('scores', {})
                        print(f"     Skills: {scores.get('skill', 0) * 100:.1f}%")
                        print(f"     Experience: {scores.get('experience', 0) * 100:.1f}%")
                        print(f"     Education: {scores.get('education', 0) * 100:.1f}%")
                        if 'location_bonus' in scores:
                            print(f"     Location: {scores.get('location_bonus', 0) * 100:.1f}%")
                else:
                    print("❌ No job matches found for this candidate")
        else:
            print("❌ Unexpected response format")
            pprint(data)
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Error connecting to API: {e}")
        
    print("\n✨ Test completed")

if __name__ == "__main__":
    test_job_matching()