import os
import re
import sys
import json
import hashlib
import requests
from bs4 import BeautifulSoup

class bcolors:
    OK = '\033[92m'
    WARN = '\033[93m'
    FAIL = '\033[91m'
    END = '\033[0m'

class Mediafire:
	def __init__(self, output_dir):
		self.ICKY_CHARS = re.compile(r'[^\w.]')
		self.OUTPUT_FOLDER = output_dir

		self.new_session()
		self.tree = {}
		self.map  = {}

	def new_session(self):
		self.session = requests.Session()
		self.session.headers = {
			"User-Agent": "Mozilla/5.0 (Windows NT 10.0; rv:68.0) Gecko/20100101 Firefox/68.0"
		}

	def download_all_files(self, folder_id):
		with open('downloads.json', 'r+') as log:
			self.checksumz = json.load(log)
			self.log = log
			self.recursive_download(folder_id)

	def soup_me_mommy(self, url, params={}):
		try:
			response = self.session.get(url, params=params)
			content_type = response.headers['content-type'].split(';')[0]
			match content_type:
				case 'application/xml':
					parser = 'xml'
				case 'text/html':
					parser = 'lxml'
			if response.status_code == 404:
				raise Exception(f'{bcolors.FAIL}[-] 404 not found, skipping:{bcolors.END} {url}')
			if response.status_code != 200 and response.status_code != 404:
				raise Exception(f'{bcolors.FAIL}[-] {url} returned unexpected response:{bcolors.END} {response.status_code}')

			soup = BeautifulSoup(response.text, parser)
			return soup
		except:
			return None

	def soup_dick(self, soup, dick):
		for element in soup.find(dick):
			yield {attr.name: attr.text for attr in element}

	def clean_string(self, string):
		return self.ICKY_CHARS.sub('_', string)

	def get_folder_id(self, url):
		raw_link = url.replace('#', '')
		download_link = raw_link.rstrip('/').split('/')[-1]
		return download_link


	def get_info(self, url):
		folder_id = self.get_folder_id(url)
		api_endpoint = 'http://www.mediafire.com/api/1.5/folder/get_info.php'
		params = {'folder_key': folder_id}
		soup = self.soup_me_mommy(api_endpoint, params)
		return list(self.soup_dick(soup, 'response'))[1]

	def get_content(self, folder_id, content_type):
		api_endpoint = 'http://www.mediafire.com/api/1.5/folder/get_content.php'
		params = {'folder_key': folder_id, 'chunk_size': 1000, 'content_type': content_type}
		soup = self.soup_me_mommy(api_endpoint, params)
		return self.soup_dick(soup, content_type)

	def get_landing_page(self, file):
		api_endpoint = 'http://www.mediafire.com/api/1.5/file/get_links.php'
		params = {'quick_key': file['quickkey']}
		soup = self.soup_me_mommy(api_endpoint, params)
		if soup is not None:
			link = soup.find('normal_download').string
			return link
		else:
			raise Exception(f'{bcolors.WARN}[-] skipping file with no info:{bcolors.END} {file}')

	def get_download_link(self, url):
		soup = self.soup_me_mommy(url)
		if soup is not None:
			link = soup.find('a', id='downloadButton')['href']
			return link
		else:
			raise Exception(f'{bcolors.WARN}[-] skipping unavailable file:{bcolors.END} {url}')

	def recursive_download(self, folder, parent_id=None):
		folder_id   = folder['folderkey']
		folder_name = folder['name']
		self.tree[folder_id] = parent_id
		self.map[folder_id]  = folder_name

		folders = self.get_content(folder_id, 'folders')
		files = self.get_content(folder_id, 'files')
		for content in folders:
			self.recursive_download(content, folder_id)
		for content in files:
			checksum = content['hash']
			raw_filename = content['filename']
			filename = self.clean_string(raw_filename)
			output_dir = self.generate_output_dir(folder_id)
			filepath = os.path.join(output_dir, filename)
			if self.checksumz.get(filepath) == checksum:
				print(f'{bcolors.WARN}[-] skipping duplicate:{bcolors.END} {filepath}')
				continue
			try:
				landing_page = self.get_landing_page(content)
				download_link = self.get_download_link(landing_page)
				self.download_file(download_link, filepath, checksum)
			except Exception as e:
				print(e)
				continue

	def generate_output_dir(self, folder_id):
		segments = []
		while True:
			segments.append(self.map[folder_id])
			parent_id = self.tree[folder_id]
			if not parent_id:
				break

			folder_id = parent_id

		segments.append(self.OUTPUT_FOLDER)
		return '/'.join(reversed([self.clean_string(x) for x in segments]))


	def download_file(self, url, filepath, advertized_checksum):
		output_dir = os.path.dirname(filepath)
		os.makedirs(output_dir, exist_ok=True)

		response = self.session.get(url)
		contents = response.content

		hasher = hashlib.sha256()
		hasher.update(contents)
		checksum = hasher.hexdigest()
		if checksum == advertized_checksum:
			self.checksumz[filepath] = checksum
			self.log.truncate()
			self.log.seek(0)
			self.log.write(json.dumps(self.checksumz, indent=4))
			self.log.flush()
		else:
			raise Exception(f'{bcolors.FAIL}[!] checksum mismatch, skipping file:{bcolors.END} {filepath}')

		print(f'{bcolors.OK}[+] writing file:{bcolors.END} {filepath}')
		with open(filepath, 'wb+') as f:
			f.write(contents)

def main(args):	
	if len(args) < 2:
		raise Exception('please provide arguments: \n1: mediafire link\n2: output directory')

	download_link = sys.argv[1]
	output_dir    = sys.argv[2]
	mediafire = Mediafire(output_dir)
	folder_id = mediafire.get_info(download_link)
	mediafire.download_all_files(folder_id)

main(sys.argv)