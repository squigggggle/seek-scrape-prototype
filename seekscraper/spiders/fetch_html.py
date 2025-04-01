import scrapy
from bs4 import BeautifulSoup
import json
from urllib.parse import urlparse, urlencode, parse_qs
import random
import time
from scrapy.downloadermiddlewares.retry import RetryMiddleware
from scrapy.utils.response import response_status_message
import os

class FetchHtmlSpider(scrapy.Spider):
    name = 'fetch_html'

    # Default parameters
    max_pages = 2  # Default: scrape up to 2 pages
    max_job_ids = 30  # Default: collect up to 30 job IDs per page

    start_urls = ['https://www.seek.co.nz/jobs-in-information-communication-technology']  # Starting URL for listings

    # Add common browser headers
    custom_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0'
    }
    
    # List of user agents to rotate
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0'
    ]

    def __init__(self, max_pages=None, max_job_ids=None, *args, **kwargs):
        super(FetchHtmlSpider, self).__init__(*args, **kwargs)

        # Set max_pages and max_job_ids from the command-line arguments if provided
        if max_pages is not None:
            self.max_pages = int(max_pages)
        if max_job_ids is not None:
            self.max_job_ids = int(max_job_ids)

    def start_requests(self):
        headers = self.custom_headers.copy()
        headers['User-Agent'] = random.choice(self.user_agents)
        yield scrapy.Request(self.start_urls[0], headers=headers)

    def parse(self, response):
        # Add random delay between requests
        time.sleep(random.uniform(2, 5))

        # Step 1: Clean the HTML by removing unwanted elements
        soup = BeautifulSoup(response.text, 'html.parser')

        # Remove unnecessary tags like script, style, nav, footer, header, svg, head
        for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'svg', 'head', 'img']):
            tag.decompose()

        for tag in soup.find_all(True):
            tag.attrs = {key: value for key, value in tag.attrs.items() if key not in ["class", "id"]}

        formatted_html = soup.prettify()
        with open('cleaned_page.html', "w", encoding='utf-8') as f:
            f.write(formatted_html)

        # Step 2: Extract job IDs from the page
        job_listings = self.extract_job_ids(soup)

        # Debugging: Log the extracted job IDs to see what is being captured
        self.logger.debug(f"Extracted job listings: {job_listings}")

        # Step 3: If no job IDs are found, stop the scrape
        if not job_listings:
            self.logger.info("No job IDs found on this page, ending the scrape.")
            return  # Stops the spider from continuing to the next page

        # Step 4: Save the job IDs to a file
        self.save_job_ids_to_file(job_listings)

        # Step 5: Handle pagination by incrementing the page number
        current_page = self.get_current_page(response.url)
        if current_page >= self.max_pages:
            self.logger.info(f"Reached the maximum number of pages ({self.max_pages}), stopping.")
            return  # Stop if we've reached the max number of pages

        next_page_url = self.get_next_page_url(response.url)
        if next_page_url:
            headers = self.custom_headers.copy()
            headers['User-Agent'] = random.choice(self.user_agents)
            yield scrapy.Request(
                next_page_url, 
                callback=self.parse,
                headers=headers,
                dont_filter=True,
                meta={
                    'dont_retry': False,
                    'max_retries': 3
                }
            )

    def extract_job_ids(self, soup):
        job_listings = []

        # Find all divs with data-search-sol-meta
        divs_with_data = soup.find_all('div', {'data-search-sol-meta': True})

        for div in divs_with_data:
            try:
                # Parse the JSON data from data-search-sol-meta attribute
                meta_data = json.loads(div['data-search-sol-meta'])
                
                # Extract and format the required fields
                job_listing = {
                    'jobId': meta_data['jobId'],
                    'searchRequestToken': meta_data['searchRequestToken'].replace('-', '')
                }
                
                job_listings.append(job_listing)

            except (json.JSONDecodeError, KeyError) as e:
                self.logger.error(f"Error processing job listing: {e}")

            if len(job_listings) >= self.max_job_ids:
                break

        return job_listings

    def save_job_ids_to_file(self, job_listings):
        filename = 'job_ids.json'
        existing_data = []

        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                try:
                    existing_data = json.load(f)
                except json.JSONDecodeError:
                    existing_data = []

        # Add only unique entries based on jobId
        existing_job_ids = {item['jobId'] for item in existing_data}
        unique_new_listings = [
            listing for listing in job_listings 
            if listing['jobId'] not in existing_job_ids
        ]

        combined_data = existing_data + unique_new_listings

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(combined_data, f, indent=2)

    def get_current_page(self, url):
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        return int(query_params.get('page', [1])[0])

    def get_next_page_url(self, current_url):
        parsed_url = urlparse(current_url)
        query_params = parse_qs(parsed_url.query)

        # Increment the page number
        current_page = int(query_params.get('page', [1])[0])
        next_page = current_page + 1
        query_params['page'] = str(next_page)

        # Rebuild the URL with the updated 'page' parameter
        new_url = parsed_url._replace(query=urlencode(query_params, doseq=True)).geturl()

        return new_url if self.has_next_page(parsed_url) else None

    def has_next_page(self, parsed_url):
        # This can be customized to check whether the 'Next' button exists or other criteria
        return True  # Assuming there's always a next page for this example
