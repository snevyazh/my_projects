import chardet
from bs4 import BeautifulSoup


file_name = "/Users/snevyazh/Downloads/Джон Фаулз/Волхв/John Fowles Magus.fb2"
with open(file_name, 'rb') as fb2file:
    fb2_content = fb2file.read()

encoding_of_the_file = chardet.detect(fb2_content)['encoding']
print(encoding_of_the_file)

with open(file_name, 'r+', encoding=encoding_of_the_file) as fb2file:
    fb2_content = fb2file.read()
soup = BeautifulSoup(fb2_content, "xml")
body = soup.find('body').prettify() if soup.find('body') else None
print(body[:200])