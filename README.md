# Ina Device Hub

Ina Device Hub manages network-connected sensor devices. It collects data such as temperature, TDS, pH and camera images and stores them in the database.

## Setup

This project is managed by [Rye](https://rye.astral.sh/guide/installation/). After installing Rye, sync the environment:

```bash
rye sync
```

### Environment Variables

Copy `.default.env` to `.env` and update the values for your environment.

```bash
cp .default.env .env
```

### Database

The project uses TursoDB. Create the database with:

```bash
rye run db:create
```

### Migrations

TODO: Add migration instructions

### Run

Start the backend and frontend servers:

```bash
rye run backend
rye run frontend
```

The application will be available at `http://localhost:5151`.

### systemd

You can use the provided systemd service file to run the project automatically on boot. Update `WorkingDirectory`, `ExecStart` and `User` to match your environment.

```bash
sudo cp ./systemd/inas-device-hub@.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable inas-device-hub@backend
sudo systemctl start inas-device-hub@backend
sudo systemctl enable inas-device-hub@frontend
sudo systemctl start inas-device-hub@frontend
```

Enjoy!
