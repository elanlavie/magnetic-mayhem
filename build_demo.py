from pathlib import Path
import json
root=Path(__file__).parent
html=(root/'public/index.html').read_text()
style=(root/'public/style.css').read_text()
script=(root/'public/app.js').read_text()
pack=(root/'public/curriculum.json').read_text().replace('</','<\\/')
html=html.replace('<link rel="stylesheet" href="style.css">','<style>'+style+'</style>')
html=html.replace('<script src="app.js"></script>','<script>window.MM_STANDALONE=true;window.MM_BUILTIN='+pack+';</script><script>'+script.replace('</script','<\\/script')+'</script>')
(root/'Magnetic_Mayhem_Demo.html').write_text(html)
print('Built Magnetic_Mayhem_Demo.html')
