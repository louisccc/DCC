import sys
import threading
import time
import queue
from pathlib import Path
import csv
import shutil
from zipfile import ZipFile
import subprocess
import traceback
from argparse import Namespace
from apscheduler.schedulers.blocking import BlockingScheduler


sys.path.append('../')
from config.config import LightWeightMethodConfig
from core.graphlightweight import TFTokenExplorer
from config.config import PWCConfigArgParser, PWCConfig
from core.paperswithcode import PWCScraper
from script.script_lightweight import preprocess, run_lightweight_method, copy_files, save_metadata


def extract_code(dir_path):
    zip_path = list(Path(dir_path).glob('*.zip'))[0]
    extract_name = (zip_path.name).split('.')[0]
    extract_path = Path(dir_path) / extract_name
    # remove directory if it already exists
    if extract_path.exists():
        shutil.rmtree(extract_path)
    # unzip file
    with ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(extract_path)
    return extract_path

def run_lightweight(paper: dict, out_path: Path, out_types: list):

    success = "N/A"
    error_msg = "N/A"

    code_path = extract_code(paper['stored_dir_path'])
    preprocess(code_path)

    args = Namespace(code_path=code_path, is_dataset=False, dest_path=".",
                     combined_triples_only=False,
                     output_types=[1, 3, 5, 6], show_arg=True, show_url=True)
    config = LightWeightMethodConfig(args)

    success, error_msg = run_lightweight_method(code_path, config)
    for filetype in out_types:
        copy_files(code_path, out_path, filetype, 8)
        
    return success, error_msg

def service(scraper: PWCScraper):
    print("Starting Hourly Scraper...")
    output_path = Path("./output").resolve()
    output_types = ['*.triples', '*.html', '*.rdf']
    scraper.scrape()
    while True:
        try:
            paper = scraper.tf_papers.get_nowait()
            success, err_msg = run_lightweight(paper, output_path, output_types)
            scraper.database.update_query(paper['stored_dir_name'], success, err_msg)
        except queue.Empty:
            break

def email_metadata(scraper: PWCScraper):
    print("Sending Daily MetaData Report...")
    metadata = scraper.database.get_table()
    file_path = Path("../metadata.csv").resolve()
    save_metadata(metadata, file_path)
    scraper.reporter.send_email("Daily Metadata Report", 
                                "CSV file with metadata is attached along with this mail.",
                                (file_path,))
    
def service_scrape_papers(args):
    config = PWCConfig(PWCConfigArgParser().get_args(args))
    config.tot_paper_to_scrape_per_shot = -1
    scraper = PWCScraper(config)

    scheduler = BlockingScheduler()
    scheduler.add_job(service, 'interval', args=(scraper,), hours=1)
    scheduler.add_job(email_metadata, 'interval', args=(scraper,), days=1)

    scheduler.start()

if __name__ == "__main__":
    service_scrape_papers(sys.argv[1:])
