# pplx-oai
openai-compatible endpoint for perplexity

# features
- use perplexity with openai-compatible interfaces like open webui
- works with or without perplexity account (cookies optional)
- supports all modes and models (requires cookies with appropriate subscription)
- best-effort citation formatting ([perplexity-ai](https://github.com/helallao/perplexity-ai) doesn't return citation links)

# sources
use different sources by adding /sources:web, /sources:social, or /sources:scholar to your message

# how to use
1. install python3
2. install the perplexity-ai library: `git clone https://github.com/helallao/perplexity-ai.git && pip install -e ./perplexity-ai`
3. install requirements: `pip install -r requirements.txt`
4. (optional) paste all your cookie from your account using [this guide](https://github.com/helallao/perplexity-ai#how-to-get-cookies) and put them in cookies.txt
5. start the app: `python3 app.py`
6. connect your openai-compatible client to http://localhost:5000

# how to use (dockerized)
1. install docker
2. build the image: `docker build -t pplx-oai .`
3. (optional) adjust the docker-compose.yml, like e.g. binding ports or changing cookies.txt location
4. start it using docker compose: `docker compose up -d`
5. connect your openai-compatible client to http://pplx-oai:5000
