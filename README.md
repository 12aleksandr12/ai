# AI Interface

## Description

This project is a Python application utilizing Docker containerization. It includes the core application logic, chat modules with GPT and Ollama, as well as styles for the user interface. The interface is configured to use the Ollama API in a local environment.

---

## Usage

### Running with Docker Compose

1. Build the container:

   ```bash
   docker compose build
   ```

2. Start the container:

    ```bash
    docker compose up -d
    ```

The application will be available at: [http://localhost:7860](http://localhost:7860).

---

## Technology Stack

- **Python 3.9** ([https://www.python.org/](https://www.python.org/))
- **Docker/Docker Compose** ([https://www.docker.com/](https://www.docker.com/)) Version 4.37.2
- **CSS** (for interface styling)
- **Ollama API** ([https://ollama.com/search](https://ollama.com/search))

---

## License

This project is distributed under the MIT license. See more details in the [LICENSE](./LICENSE) file.

