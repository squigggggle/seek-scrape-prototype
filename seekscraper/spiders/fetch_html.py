import scrapy
from bs4 import BeautifulSoup
import json
from urllib.parse import urlparse, urlencode

class FetchHtmlSpider(scrapy.Spider):
    name = 'fetch_html'

    # Default parameters
    max_pages = 5  # Default: scrape up to 5 pages
    max_job_ids = 10  # Default: collect up to 10 job IDs per page

    start_urls = ['https://www.seek.co.nz/jobs-in-information-communication-technology?page=1']  # Starting URL for listings

    def __init__(self, max_pages=None, max_job_ids=None, *args, **kwargs):
        super(FetchHtmlSpider, self).__init__(*args, **kwargs)

        # Set max_pages and max_job_ids from the command-line arguments if provided
        if max_pages is not None:
            self.max_pages = int(max_pages)
        if max_job_ids is not None:
            self.max_job_ids = int(max_job_ids)

    def parse(self, response):
        # Step 1: Clean the HTML by removing unwanted elements
        soup = BeautifulSoup(response.text, 'html.parser')

        # Remove unnecessary tags like script, style, and other elements
        for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
            tag.decompose()

        # Step 2: Extract job IDs from the page
        job_ids = self.extract_job_ids(soup)

        # Debugging: Log the extracted job IDs to see what is being captured
        self.logger.debug(f"Extracted job IDs: {job_ids}")

        # Step 3: If no job IDs are found, stop the scrape
        if not job_ids:
            self.logger.info("No job IDs found on this page, ending the scrape.")
            return  # Stops the spider from continuing to the next page

        # Step 4: Save the job IDs to a file
        self.save_job_ids_to_file(job_ids)

        # Step 5: Handle pagination by incrementing the page number
        current_page = self.get_current_page(response.url)
        if current_page >= self.max_pages:
            self.logger.info(f"Reached the maximum number of pages ({self.max_pages}), stopping.")
            return  # Stop if we've reached the max number of pages

        next_page_url = self.get_next_page_url(response.url)
        if next_page_url:
            yield scrapy.Request(next_page_url, callback=self.parse)

    def extract_job_ids(self, soup):
        job_ids = []

        # Step 1: Search for divs with the 'data-search-sol-meta' attribute
        divs_with_data = soup.find_all('div', {'data-search-sol-meta': True})

        # Step 2: Extract the jobId from the 'data-search-sol-meta' attribute
        for div in divs_with_data:
            data_search_sol_meta = div.get('data-search-sol-meta')
            try:
                # Parse the JSON inside the 'data-search-sol-meta' string
                meta_data = json.loads(data_search_sol_meta)
                job_id = meta_data.get('jobId')
                if job_id:
                    job_ids.append(job_id)
            except json.JSONDecodeError as e:
                self.logger.error(f"Error decoding JSON in 'data-search-sol-meta': {e}")

            # Stop if we've reached the max number of job IDs to collect per page
            if len(job_ids) >= self.max_job_ids:
                break

        return job_ids

    def save_job_ids_to_file(self, job_ids):
        with open('job_ids.json', 'a', encoding='utf-8') as f:
            for job_id in job_ids:
                f.write(f"{job_id}\n")  # Write each job_id on a new line

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
