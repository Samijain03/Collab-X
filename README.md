# Collab-X 🤝

Collab-X is a modern, real-time chat application designed for seamless communication and collaboration. Built with Python and Django, this project aims to provide a secure and feature-rich platform for users to connect with friends, family, and colleagues.

-----

## ✨ Features

The application is currently under active development. Here is a list of implemented and planned features:

#### Implemented

- **User Authentication:** Secure user registration and login system (email/password).
- **Dynamic Dashboard:** A responsive, two-column dashboard that serves as the main user interface.
- **Contact Management:** Users can search for other users and add them to their personal contact list.
- **Real-Time One-to-One Messaging:** Instant messaging using Django Channels and WebSockets.

#### Planned

- **Group Chat Functionality:** Create and manage group conversations with multiple members.
- **Voice and Video Calls:** Peer-to-peer calls using WebRTC.
- **End-to-End Encryption:** Ensuring the privacy and security of all conversations.

-----

## 🚀 Getting Started

To get a local copy up and running, follow these simple steps.

### Prerequisites

Make sure you have the following installed on your system:

- Python 3.8+ and Pip
- Git

### Installation & Setup

1.  **Clone the repository:**
    ```bash
    git clone <your-repository-url>
    cd Collab-X
    ```

2.  **Create and activate a virtual environment:**
    - On Windows:
      ```bash
      python -m venv venv
      .\venv\Scripts\activate
      ```
    - On macOS/Linux:
      ```bash
      python3 -m venv venv
      source venv/bin/activate
      ```

3.  **Install the required packages:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Apply the database migrations:**
    ```bash
    python manage.py makemigrations
    python manage.py migrate
    ```

5.  **Create a superuser to access the admin panel:**
    ```bash
    python manage.py createsuperuser
    ```
    Follow the prompts to create your admin account.

6.  **Run the development server:**

    Since this project uses Django Channels, it must be run with an ASGI server like `daphne` to handle both HTTP and WebSocket traffic.

    ```bash
    daphne -p 8000 Collab_X.asgi:application
    ```

The application will be available at `http://127.0.0.1:8000/`.

### Deployment on Render

1. **Create a Web Service** connected to your repository.
2. Set the following settings:
   - **Environment**: `Python`
   - **Build Command**: `./build.sh` (or `pip install -r requirements.txt && python manage.py collectstatic --no-input`)
   - **Start Command**: `python manage.py migrate && daphne -b 0.0.0.0 -p $PORT Collab_X.asgi:application`
3. Set the following **Environment Variables** in Render:
   - `PYTHON_VERSION`: `3.12.3`
   - `SECRET_KEY`: `<your-random-secret-key>`
   - `DEBUG`: `False`
   - `DATABASE_URL`: `<your-render-postgresql-internal-or-external-url>`
   - `GOOGLE_GEMINI_API_KEY`: `<your-gemini-api-key>`
   - `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_STORAGE_BUCKET_NAME`, `AWS_S3_ENDPOINT_URL` (optional, for media uploads)
   - `REDIS_URL`: `<your-render-redis-internal-url>` (optional, for multi-worker Channels)

-----

## 👥 Team

This project is being developed by a passionate team of three:

- **Samay**
- **Kapil**
- **Prashant**

Feel free to contribute to the project by following our development pipeline.