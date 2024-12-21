{
  description = "Clang Tooling Reductions";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs =
    { self, nixpkgs, ... }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs { inherit system; };
      python-pkgs = pkgs.python312Packages;

    in
    {
      packages.${system}.default = python-pkgs.buildPythonPackage {
        pname = "reducer";
        version = "0.1";
        propagatedBuildInputs = [
          python-pkgs.rich
          python-pkgs.setuptools
        ];
        pyproject = true;
        src = ./.;
      };

      apps.${system}.default = {
        type = "app";
        program = "${self.packages.${system}.default}/bin/reducer";
      };
    };
}
