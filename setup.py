from setuptools import setup

setup(
    name='pinboardzine',
    version='1.0',
    description='Publish unread bookmarks from Pinboard for Kindle',
    py_modules=['pinboardzine'],
    scripts=['bin/pinboardzine'],

    author='Mark Paschal',
    author_email='markpasc@markpasc.org',
    url='https://github.com/markpasc/pinboardzine',
    classifiers=[
        'Environment :: Console',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
    ],

    requires=['argh', 'arghlog', 'requests'],
    install_requires=['argh', 'arghlog', 'requests'],
)
