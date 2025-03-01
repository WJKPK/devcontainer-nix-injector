{
  description = "Flake for dni (Devcontainer Nix Injector)";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { nixpkgs, flake-utils, ... }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
        dniDepedencies = pkgs.python3.withPackages (ps: with ps; [
          typer
          rich
          pkgs.devcontainer
        ]);

        dni = pkgs.python3Packages.buildPythonPackage {
            pname = "dni";
            version = "1.0";
            src = ./.;
            format = "pyproject";
            nativeBuildInputs = with pkgs.python3Packages; [ setuptools wheel ];
            propagatedBuildInputs = [ dniDepedencies ];
         };
      in
      {
        devShells.default = pkgs.mkShell {
          buildInputs = [
            dniDepedencies
            pkgs.ruff
          ];
          
          shellHook = ''
            echo "dni (Devcontainer Nix Injector) development environment"
          '';
        };
        packages.default = dni;
      }
    );
}

