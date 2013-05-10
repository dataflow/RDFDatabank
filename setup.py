try:
    from setuptools import setup, find_packages
except ImportError:
    from ez_setup import use_setuptools
    use_setuptools()
    from setuptools import setup, find_packages

setup(
    name='rdfdatabank',
    version='1.0.2',
    description='A pairtree enhanced, rdf backed data store used to archive, publish and access data from the web using a restful api.',
    author='The DataFlow Project',
    author_email='jisc.dataflow@gmail.com',
    install_requires=[
        "Pylons==1.0",
        "python-dateutil==1.5",
        "pairtree==0.7.1-T",
        "solrpy==0.9.5",
        "rdflib==2.4.2",
        "redis==2.4.11",
        "lxml==2.3.4",
        "sqlalchemy==0.7.6",
        "uuid"
    ],
    setup_requires=["PasteScript>=1.6.3", "Pylons==0.9.7", "pairtree==0.7.1-T", "rdfobject", "recordsilo", "simplejson", "redis"],
    packages=find_packages(exclude=['ez_setup']),
    include_package_data=True,
    test_suite='nose.collector',
    package_data={'rdfdatabank': ['i18n/*/LC_MESSAGES/*.mo']},
    #message_extractors={'rdfdatabank': [
    #        ('**.py', 'python', None),
    #        ('templates/**.mako', 'mako', {'input_encoding': 'utf-8'}),
    #        ('public/**', 'ignore', None)]},
    zip_safe=False,
    paster_plugins=['PasteScript', 'Pylons'],
    entry_points="""
    [paste.app_factory]
    main = rdfdatabank.config.middleware:make_app

    [paste.app_install]
    main = pylons.util:PylonsInstaller
    """,
)
