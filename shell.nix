{ pkgs ? import <nixpkgs> {} }:

let
  pythonWithPackages = pkgs.python3.withPackages (ps: with ps; [
    flask
    flask-cors
    google-cloud-firestore
    google-api-python-client
    (pkgs.python3Packages.wordcloud.overrideAttrs (oldAttrs: {
      checkPhase = ''
        # The original check phase is causing issues, so we skip it.
      '';
    }))
    pandas
    gunicorn
    requests
    sendgrid
    google-cloud-secret-manager
    beautifulsoup4
    jinja2
    google-generativeai
    tweepy
    praw
  ]);
in
pkgs.mkShell {
  buildInputs = [
    pythonWithPackages
    pkgs.nodejs_20
  ];
}
