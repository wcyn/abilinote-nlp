import sqlite3, re, sys, http.client, time, nltk, string
from http.cookiejar import CookieJar
import urllib.request, datetime
from urllib.request import urlopen
from bs4 import BeautifulSoup

cj = CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
opener.addheaders = [('User-agent', 'Mozilla/5.0')]
url_root = 'https://en.wikipedia.org'
starting_word = 'Glossary_of_artificial_intelligence'
starting_word_val = 1

def get_wiki_glossary_links():
	url = 'https://en.wikipedia.org/wiki/Glossary_of_artificial_intelligence'
	link_dict = dict()
	try:
		data = opener.open(url).read()
		data = data.decode('utf-8', 'ignore')
	except Exception as e:
		print('failed in get_wiki_links_from_source_soup main loop')
		print(str(e))
	key_word_links = ''.join(re.findall(r'<li><b>(.*)</b> \u2013</li>', data))
	soup = BeautifulSoup(key_word_links, "html5lib")
	for link in soup.findAll('a'):
		title = link.contents[0].string
		href = link.get('href')
		link_dict.update({title.lower(): href})
	return link_dict

glosary_links = get_wiki_glossary_links()
parent_linkset = set(['/wiki/'+starting_word])
visited_key_words = set()

url =  url_root + '/wiki/Artificial_intelligence'
punctuations = '''!()-[]{};:'"\,<>./?@#$%^&*_~'''

try:
	import psycopg2
	conn = psycopg2.connect("dbname='abilinote_kbase' user='wcyn' host='localhost' password='12345678'")
	c = conn.cursor()
except Exception as e:
	print("Cannot connect to the postgresql database")
	print(str(e))

def uprint(*objects, sep=' ', end='\n', file=sys.stdout):
	try:
		enc = file.encoding
		if enc == 'UTF-8':
			print(*objects, sep=sep, end=end, file=file)
		else:
			f = lambda obj: str(obj).encode(enc, errors='backslashreplace').decode(enc)
			print(*map(f, objects), sep=sep, end=end, file=file)
	except Exception as e:
		print("Cannot encode and print answer")
		print(str(e))

def strip_tags(value):
	"""Returns the given HTML with all tags stripped."""
	return re.sub(r'<[^>]*?>', '', str(value))


def tag_text(sentences):
	try:
		print('\n\nbegun processing\n-------------------\n')
		cp = nltk.RegexpParser('CHUNK: {<NN.*> <[NN.*|VBG.*]> <VB[G|Z|P].*>}')
		cp_prep = nltk.RegexpParser('CHUNK: {<PRP>}')
		tokenized_sents = []
		for sentence in sentences:
			sentence = ''.join(e for e in sentence if e not in punctuations)
			print('\n\n\t\t ====== sentence =======')
			uprint(sentence)
			tokenized = nltk.word_tokenize(str(sentence))
			print('begun tokenizing')
			tagged = nltk.pos_tag(tokenized)
			print('tagged')
			uprint(tagged)
			tree = cp.parse(tagged)
			tree_prep = cp_prep.parse(tagged)
			for subtree in tree.subtrees():
				if subtree.label() == 'CHUNK':
					uprint(subtree)
					key_words = re.findall(r'\(CHUNK (\w*)/NN.* (\w*)[/VBG|/NN.*]+ ', str(subtree))
					uprint("keywords: %s" % key_words)

			for subtree in tree_prep.subtrees():
				if subtree.label() == 'CHUNK':
					uprint(subtree)
					prepositions = re.findall(r'\(CHUNK (\w*)/PRP', str(subtree))
					uprint("prepositions: %s" % prepositions)
	except Exception as e:
		print("Failed tag_text function")
		print(str(e))
		conn.rollback()

def add_glossary_links_to_visited_key_words(link_dict):
	global visited_key_words

	visited_key_words = visited_key_words.union(link_dict)
	
def get_wiki_links_from_source_soup(soup):
	link_dict = dict()
	try:
		if soup:
			for a in soup.findAll('a'):
				if a.parent.name == 'p':
					link_dict.update({a.text.replace('"',''):a['href']})
			return link_dict
		else: return {}
	except Exception as e:
		print('failed in get_wiki_links_from_source_soup')
		print(str(e))
		return {}
	
def get_wiki_page_source_soup(url):
	try:    
		data = opener.open(url).read()
		data = data.decode('utf-8', 'ignore')
		soup = BeautifulSoup(data, "html5lib")
		return soup
	except Exception as e:
		print('failed in get_wiki_page_source_soup')
		print(str(e))
		return None

def get_word_definition_from_wiki(text_list):
	definition = 'No definition yet'
	try:
		if len(text_list) > 1:
			definition = '. '.join(text_list[:2]) + '.'
		elif len(text_list) == 1:
			definition = '. '.join(text_list[:2]) + '.'
	except IndexError as e:
		print('Index out of range: %s' % str(e))
	except Exception as e:
		print('Something went wrong: %s' % str(e))
	return definition

def get_sentences_from_soup(soup, limit=-1):
	lines_of_interest = []
	text_source = ''
	text_list = []
	count = 0
	try:
		for p in soup.find_all('p'):
			try:
				if 'mw-content-ltr' in p.parent['class']:
					# convert tags to string
					if count == limit:
						break
					for content in p.contents:
						text_source += str(content)
					text_list = BeautifulSoup(text_source, "html5lib").get_text()
					text_list = re.sub(r'\[.*?\]', '', str(text_list))
					text_list = text_list.split('. ')
					count+=1
			except KeyError as e:
				print('Attribute does not exist in parent: %s' % str(e))
	except Exception as e:
		print('Failed in get_word_definition_from_wiki. Soup Problems: %s' % str(e))

	return text_list

def get_key_words_from_url_recursive(url, word, deep, maxdeep, parent_linkset):
	global url_root
	global visited_key_words
	
	enc = 'UTF8'
	soup = get_wiki_page_source_soup(url)
	link_dict = get_wiki_links_from_source_soup(soup)
	link_dict = { key : value for key,value in link_dict.items() if value not in parent_linkset}
	parent_linkset = link_dict
	totalhits = 0
	count = 1
	uprint('Analizing (level %i) url %s' %(deep,url))
	print('\n\t\t##### Link_dict ######')
	uprint('%i links retrived' % len(link_dict))

	if deep >= maxdeep: #last iteration level
		print("Reading last iteration.")
		uprint(word)

	if deep < maxdeep: #recursive section
		if deep == 1: #initialize root - first iteration level
			try:
				query = "SELECT * FROM visited_key_words WHERE word ILIKE %s"
				c.execute(query, [(word)])
				done_data = c.fetchone()
			except Exception as e:
				print('failed in getting root select')
				print(str(e))
			if done_data is None:
				try:
					c.execute("INSERT INTO visited_key_words (word) VALUES(%s)", (word,))
					conn.commit()        	
				except Exception as e:
					print('failed to insert root into visited_key_words. Rolling back...')
					print(str(e))
					conn.rollback()
			# Add root into word_vals relation
			try:
				query = "SELECT * FROM word_vals WHERE word ILIKE %s"
				c.execute(query, [(word)])
				word_vals_data = c.fetchone()
			except Exception as e:
				print('failed in root word query select')
				print(str(e))

			if word_vals_data is None:
				print("root word not here yet, let us add it...")
				key_soup = get_wiki_page_source_soup(url)
				definition = get_word_definition_from_wiki(get_sentences_from_soup(key_soup, 1))
				uprint('\n\t\t^^^^^^ Definition ^^^^^^\n')
				uprint(definition)
				try:
					c.execute("INSERT INTO word_vals(word, level, parent_word, definition, link) VALUES (%s, %s, %s, %s, %s)",
						(word, starting_word_val, None, definition, url))
					conn.commit()                	
				except Exception as e:
					print('Failed in insert root word into word_vals. Rolling back...')
					print(str(e))
					conn.rollback()
					# try again with default definition
					try:
						definition = '-No Definition Yet-'
						c.execute("INSERT INTO word_vals(word, level, parent_word, definition, link) VALUES (%s, %s, %s, %s, %s)",
							(word, starting_word_val, None, definition, url))
						conn.commit()  
						print('Second insert successful')
					except Exception as e:
						print('Failed in second insert into root word into word_vals. Rolling back...')
						print(str(e))
						conn.rollback()
			pass


		for title, link in link_dict.items():
			if title not in visited_key_words:
				uprint("%s not here yet, let us recurse through it..." % title)
				uprint("There are %i links, going recursive into link number %i at url %s" % (len(link_dict), count, url_root + link))
				get_key_words_from_url_recursive(url_root + link, title, deep+1, maxdeep, parent_linkset)            

			else:
				uprint("\n*** Word '%s' already done. Skipping recursion into it ***" %text)

			# Add new keyword into postgresql db
			try:
				query = "SELECT * FROM word_vals WHERE word ILIKE %s"
				c.execute(query, [(title)])
				data = c.fetchone()
			except Exception as e:
				print('failed in query select')
				print(str(e))

			if data is None:
				uprint("%s word not here yet, let us add it to postgres...: " % title)
				key_soup = get_wiki_page_source_soup(url_root + link)
				definition = get_word_definition_from_wiki(get_sentences_from_soup(key_soup, 1))
				uprint('\n\t\t^^^^^ Definition ^^^^^^\n')
				uprint(definition)
				try:
					c.execute("INSERT INTO word_vals(word, level, parent_word, definition, link) VALUES (%s, %s, %s, %s, %s)",
						(title, starting_word_val + deep, word, definition, url_root + link))
					conn.commit()                	
				except Exception as e:
					print('Failed in insert into word_vals. Rolling back...')
					print('\n\n\t ERROR!: %s :!' %str(e))
					conn.rollback()
					# try again with default definition
					try:
						definition = '-No Definition Yet-'
						c.execute("INSERT INTO word_vals(word, level, parent_word, definition, link) VALUES (%s, %s, %s, %s, %s)",
							(title, starting_word_val + deep, word, definition, url_root + link))
						conn.commit()   
						print('Second insert successful')
					except Exception as e:
						print('Failed in second insert into word_vals. Rolling back...')
						print('\n\n\t ERROR!: %s :!' %str(e))
						conn.rollback()
					
			else:
				uprint('Word %s already in postgres' %title)

			count+=1
		try:
			query = "SELECT * FROM visited_key_words WHERE word ILIKE %s"
			c.execute(query, [(word)])
			data = c.fetchone()
		except Exception as e:
			print('failed in visited_key_words query select')
			print(str(e))
				

		if data is None:
			uprint("%s not visited yet, let us recurse through it... " % word)
			try:
				uprint('inserting %s word into visited_key_words: ' % word)
				c.execute("INSERT INTO visited_key_words (word) VALUES(%s)", (word,))
				conn.commit()        	
				visited_key_words.add(word)
			except Exception as e:
				print('failed in base case. Rolling back...')
				print(str(e))
				conn.rollback()
			
		print("Leaving link_dict...")
	return

def main():	
	print("\n\n\t*********** STARTING SPIDER_PEDIA ************\n")

	for title, link in glosary_links.items():
		print("key: %s, value: %s" %(title, link))
		get_key_words_from_url_recursive(url_root + link, title, 1, 2, parent_linkset)
	print('Done!')


if __name__ == '__main__':
	main()