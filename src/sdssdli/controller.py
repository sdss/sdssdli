#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2023-07-21
# @Filename: controller.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import pathlib
import re
import warnings

import httpx
from case_insensitive_dict import CaseInsensitiveDict

from sdsstools import read_yaml_file


__all__ = ["DLIController"]


class DLIController:
    """Controller class for a Digital Loggers power switch.

    Parameters
    ----------
    name
        Name associated with this DLI controller.
    host
        The address to connect to the DLI switch.
    user
        The username to use for connecting to the DLI switch.
    port
        The port for the connection. Default to the HTTP port.
    password
        The password for the user. Alternatively it can be a path
        to a YAML secrets file. In this case the password must be
        defined as ``dli.<name>.<user>`` where ``<name>`` is the
        name assigned to the controller, and ``<user>`` is the
        username used to connect to it. Defaults to
        ``~/.secrets.yaml``.

    """

    def __init__(
        self,
        name: str,
        host: str,
        user: str,
        port: int = 80,
        password: str | pathlib.Path | None = None,
    ):
        self.name = name
        self.host = host
        self.port = port
        self.user = user

        if password is None:
            password = "~/.secrets.yaml"

        if pathlib.Path(password).expanduser().is_file():
            secrets_data = read_yaml_file(pathlib.Path(password).expanduser())
            password_tmp = secrets_data.get("dli", {}).get(name, {}).get(user)
            if password_tmp is not None:
                password = str(password_tmp)
            else:
                if isinstance(password, pathlib.Path):
                    raise ValueError("Cannot find password file or user data.")

        # Assume the password is not a file.
        password = str(password)

        # Private variable.
        self.__password = password

        self._name_to_outlet: CaseInsensitiveDict[str, int] = CaseInsensitiveDict()
        self._outlet_to_name: dict[int, str] = {}

    def _get_client(self):
        """Returns a one-time client."""

        auth = httpx.DigestAuth(self.user, self.__password)

        return httpx.AsyncClient(
            auth=auth,
            base_url=f"http://{self.host}:{self.port}/restapi",
        )

    async def get(self, route: str, **kwargs):
        """Sends a GET request to the DLI API."""

        async with self._get_client() as client:
            r = await client.get(route, **kwargs)
            r.raise_for_status()

            if r.is_success:
                return r.json()

    async def put(self, route: str, **kwargs):
        """Sends a PUT request to the DLI API."""

        async with self._get_client() as client:
            r = await client.put(route, **kwargs)
            r.raise_for_status()
            print(r.text)

        return True

    async def is_connected(self):
        """Checks if the DLI is responding to requests."""

        try:
            await self.get("/relay/outlets/=0/state/")
            return True
        except httpx.HTTPError:
            return False

    async def reload(self):
        """Reloads the internal information about the outlets."""

        data = await self.get(
            "/relay/outlets/all;/name/",
            headers={"Accept": "application/json"},
        )

        assert isinstance(data, list)

        self._name_to_outlet = CaseInsensitiveDict(zip(data, range(len(data))))
        self._outlet_to_name = dict(zip(range(len(data)), data))

    def get_outlet_number(self, name: str, use_fuzzy: bool = True) -> int:
        """Get the 0-indexed outlet number from an outlet name.

        Parameters
        ----------
        name
            The name of the outlet.
        use_fuzzy
            The `True`, and the name does not match an outlet name in a
            case-insensitive match, will try to find a match for the
            named outlet as long as the match is unambiguous. The outlet
            name must always match the query string.

        Returns
        -------
        outlet
            The number of the outlet (0-indexed, as expected by the REST API).

        """

        if name in self._name_to_outlet:
            return self._name_to_outlet[name]

        if not use_fuzzy:
            raise ValueError(f"Cannot find a matching outlet for {name!r}.")

        if len(name) < 2:
            raise ValueError("At least two characters are required for fuzzy matching.")

        n_matches: int = 0
        last_match: int = 0

        for oname, outlet in self._name_to_outlet.items():
            if re.match(rf"^{name}", oname, re.IGNORECASE):
                n_matches += 1
                last_match = outlet

        if n_matches == 0:
            raise ValueError(f"Cannot find a matching outlet for {name!r}.")
        elif n_matches > 1:
            raise ValueError(f"Multiple outlet matches found for {name!r}.")

        return last_match

    def _get_outlet_indices(self, outlets: int | str | list[str | int]):
        """Returns a list of outlet indices from variable inputs."""

        if isinstance(outlets, (int, str)):
            outlets = [outlets]

        indices: list[int] = []
        for outlet in outlets:
            if isinstance(outlet, int):
                indices.append(outlet)
            else:
                indices.append(self.get_outlet_number(outlet))

        return indices

    async def _switch(self, outlets: int | str | list[str | int], value: bool):
        """Switches an outlet on/off.

        Parameters
        ----------
        outlets
            The 0-indexed outlet number, the outlet name, or a list of outlets
            to turn on/off.
        value
            `True` to turn the switch(es) on, `False` for off.

        """

        await self._check_outlets()

        if outlets == "all":
            outlets_route = "all;"
        else:
            indices = self._get_outlet_indices(outlets)
            if len(indices) == 0:
                raise ValueError("No outlets defined.")

            outlets_route = "=" + ",".join(map(str, indices))

        await self.put(
            f"/relay/outlets/{outlets_route}/state/",
            data={"value": value},
            headers={"X-CSRF": "x"},
        )

        return True

    async def _check_outlets(self):
        """Attempts a reload of the outlets if none are present."""

        if len(self._name_to_outlet) > 0:
            return

        warnings.warn("No outlets found. Trying to reload.", UserWarning)
        await self.reload()

        if len(self._name_to_outlet) == 0:
            raise ValueError("No outlets found.")

    async def state(
        self,
        outlets: int | str | list[str | int] = "all",
    ) -> dict[str, int]:
        """Returns the state of the outlets.

        Parameters
        ----------
        outlets
            The 0-indexed outlet number, the outlet name, or a list of outlets.
            If ``"all"``, returns the state of all the outlets.

        Returns
        -------
        state
            A dictionary of outlet name to state.

        """

        await self._check_outlets()

        if outlets == "all":
            outlets_route = "all;"
            names = list(self._name_to_outlet)
        else:
            indices = self._get_outlet_indices(outlets)
            if len(indices) == 0:
                raise ValueError("No outlets defined.")

            outlets_route = "=" + ",".join(map(str, indices))
            names = [self._outlet_to_name[outlet] for outlet in indices]

        states = await self.get(f"/relay/outlets/{outlets_route}/state/")
        assert isinstance(states, list)

        return dict(zip(names, states))

    async def on(self, outlets: int | str | list[str | int]):
        """Turns on a series of outlets.

        Parameters
        ----------
        outlets
            The 0-indexed outlet number, the outlet name, or a list of outlets
            to turn on. If ``"all"``, all the outlets will be turned on.

        """

        return await self._switch(outlets, True)

    async def off(self, outlets: int | str | list[str | int]):
        """Turns off a series of outlets.

        Parameters
        ----------
        outlets
            The 0-indexed outlet number, the outlet name, or a list of outlets
            to turn off. If ``"all"``, all the outlets will be turned off.

        """

        return await self._switch(outlets, False)
