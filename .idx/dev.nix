{pkgs}: {
  channel = "stable-24.05";
  packages = [
    pkgs.nodejs_20
    pkgs.python3
    pkgs.python3Packages.pip
    pkgs.python3Packages.flask
    pkgs.python3Packages.flask-cors
    pkgs.python3Packages.requests
    pkgs.python3Packages.beautifulsoup4
    pkgs.python3Packages.google-generativeai
    pkgs.python3Packages.google-cloud-firestore
    pkgs.python3Packages.google-api-python-client
    pkgs.python3Packages.wordcloud
    pkgs.python3Packages.pandas
    pkgs.python3Packages.gunicorn
    pkgs.python3Packages.google-cloud-secret-manager
    pkgs.python3Packages.tweepy
    pkgs.python3Packages.praw
  ];
  idx.extensions = [
    "svelte.svelte-vscode"
    "vue.volar"
  ];
  idx.previews = {
    previews = {
      web = {
        command = [
          "npm"
          "run"
          "start"
        ];
        env = {
          PORT = "$PORT";
        };
        manager = "web";
      };
    };
  };
}