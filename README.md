Here is the updated `README.md` file.

I've moved **Group Chat** from "Planned" to "Implemented" and added all the new features we built, such as **AI Integration**, **Social Logins**, and **Profile Customization**.

I also added a critical step to the **Installation** guide for setting up the `.env` file, which is required for the Gemini API key.

-----

# Collab-X 🤝

Collab-X is a modern, real-time chat application designed for seamless communication and collaboration. Built with Python and Django, this project aims to provide a secure and feature-rich platform for users to connect with friends, family, and colleagues.

-----

## ✨ Features

The application is currently under active development. Here is a list of implemented and planned features:

#### Implemented

  - **User Authentication:** Secure user registration and login system (email/password) alongside social logins (Google, Microsoft) via `django-allauth`.
  - **Profile Customization:** Users can update their display name, "About Me" bio, and upload a custom profile picture.
  - **Dynamic Dashboard:** A responsive, two-column dashboard that serves as the main user interface.
  - **Contact Management:** A full contact request system where users can search for others, send requests, and accept or decline incoming requests.
  - **Real-Time One-to-One Messaging:** Instant messaging using Django Channels and WebSockets.
  - **Real-Time Group Chat:** Users can create groups, add/remove members, and change group names.
  - **AI Assistant Integration:** Users can type `/Collab <query>` in any chat to get summaries or ask questions about the conversation, powered by the Gemini API.
  - **Message Deletion:** Users can delete their own messages, which updates in real-time for all participants.

#### Planned

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

4.  **Create your environment file:**
    Create a file named `.env` in the root project directory (where `manage.py` is). This is required for the AI features.

    ```.env
    SECRET_KEY=your-django-secret-key-goes-here
    GOOGLE_GEMINI_API_KEY=your-gemini-api-key-goes-here
    ```

5.  **Apply the database migrations:**

    ```bash
    python manage.py makemigrations
    python manage.py migrate
    ```

6.  **Create a superuser to access the admin panel:**

    ```bash
    python manage.py createsuperuser
    ```

    Follow the prompts to create your admin account.

7.  **Run the application server:**

    Since this project uses Django Channels, it must be run with an ASGI server like `daphne` to handle both HTTP and WebSocket traffic.

    ```bash
    daphne -p 8000 Collab_X.asgi:application
    ```

The application will be available at `http://127.0.0.1:8000/`.

-----

## 👥 Team

This project is being developed by a passionate team of three:

  - **Samay**
  - **Kapil**
  - **Prashant**

Feel free to contribute to the project by following our development pipeline.