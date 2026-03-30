import logging
import sys
from scraper import scrape_google_maps

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def test_scrape():
    print("Starting test scrape...")
    try:
        # Run a small scrape job
        # Assuming scrape_google_maps returns a generator or list
        results = scrape_google_maps(
            keyword="dentist",
            location="New York",
            max_results=2, # Keep it very small
            enrich_socials=True,
            enrich_facebook_emails=True,
            website_max_pages=1
        )
        
        print(f"Scrape completed. Found {len(results)} results.")
        for result in results:
            print(f"Name: {result.get('name')}")
            print(f"Emails: {result.get('emails')}")
            print(f"Socials: {result.get('facebook_url')}, {result.get('instagram_url')}")
            
    except Exception as e:
        print(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_scrape()
