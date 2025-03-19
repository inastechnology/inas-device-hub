# ina-device-hub

Ina deivice hub is a project to manage the sensor devices in a network. We get the data, such as temperature, tds, ph, camera images, etc., from the devices and store them in the database. 


## setup 

This project is managed by rye. To install rye

[Rye Installation](https://rye.astral.sh/guide/installation/)

And then run the following command to sync the project

```bash
rye sync
```

### Environment Variables

The environment variables are stored in the `.env` file. You can copy the `.default.env` file to `.env` and update the values.

```bash
cp .default.env .env
```

### Database

The project uses TursoDB as the database. You can create the database by running the following command.

```bash
rye run db:create
```

### Migrations

TODO: Add migration instructions

### Run

We can run the project using the following command.

```bash
rye run serve
```

And the project will be running on `http://localhost:5151`

### systemd

you can use the following systemd service file to run the project automatically on boot.

> [!IMPORTANT]
> Make sure to update the `WorkingDirectory` and `ExecStart` values in the service file.
> you should change the "/home/inas-usr/ina-device-hub" to the path of the project.

```bash
sudo cp ./systemd/inas-device-hub.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable inas-device-hub
sudo systemctl start inas-device-hub
```

enjoy!

