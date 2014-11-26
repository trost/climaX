# a '-' before a shell command causes make to ignore its exit code (errors)

install:
	apt-get install python-mysqldb python-pip python-dev
	python setup.py install

uninstall:
	yes | pip uninstall climaX

clean:
	find . -name '*.pyc' -delete
	rm -rf build dist climaX.egg-info __pycache__

reinstall: clean uninstall install

lint:
	flake8 .

test:
	getClimateData.py 56878 2012-07-01 42 0.14
	getClimateData.py 44443 2011-06-01 27 0.09
