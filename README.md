# Collab-X 🤝

Collab-X is a modern, real-time chat application designed for seamless communication and collaboration. Built with Python and Django, this project aims to provide a secure and feature-rich platform for users to connect with friends, family, and colleagues.

-----

## ✨ Features

The application is currently under active development. Here is a list of implemented and planned features:

#### Implemented

  - **User Authentication:** Secure user registration and login system (email/password).
  - **Dynamic Dashboard:** A responsive, two-column dashboard that serves as the main user interface.
  - **Contact Management:** Users can search for other users and add them to their personal contact list.

#### Planned

  - **Real-Time One-to-One Messaging:** Instant messaging using Django Channels and WebSockets.
  - **Group Chat Functionality:** Create and manage group conversations with multiple members.
  - **Voice and Video Calls:** Peer-to-peer calls using WebRTC.
  - **End-to-End Encryption:** Ensuring the privacy and security of all conversations.

-----

## 🚀 Getting Started

To get a local copy up and running, follow these simple steps.

### Prerequisites

Make sure you have the following installed on your system:

  * Python 3.8+ and Pip
  * Git

### Installation & Setup

1.  **Clone the repository:**

    ```bash
    git clone <your-repository-url>
    cd Collab-X
    ```

2.  **Create and activate a virtual environment:**

      * On Windows:
        ```bash
        python -m venv venv
        .\venv\Scripts\activate
        ```
      * On macOS/Linux:
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

    ```bash
    python manage.py runserver
    ```

The application will be available at `http://127.0.0.1:8000/`.

-----

## 👥 Team

This project is being developed by a passionate team of three:

  * **Samay**
  * **Kapil**
  * **Prashant**

Feel free to contribute to the project by following our development pipeline.