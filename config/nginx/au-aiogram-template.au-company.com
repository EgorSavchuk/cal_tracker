server
{
	listen 80;
	server_name au-aiogram-template.au-company.com;

	location /webhook/
	{
		include proxy_params;
		proxy_pass http://localhost:8080;
	}

	location /payment/result-notification/
	{
		include proxy_params;
		proxy_pass http://localhost:8080;
	}

	location /
	{
		return 403;
	}
}
