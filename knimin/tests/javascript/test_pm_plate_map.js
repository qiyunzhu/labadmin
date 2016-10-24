$(document).ready(function() {
  QUnit.module('plateMap', {
      beforeEach: function(assert) {
        // this.pm = new plateMap();
      },
      afterEach: function(assert) {
        // $('.content').empty();
        // this.pm.destroy();
      }
  });

  QUnit.test('plateMap.printID', function(assert) {
    var done = assert.async();
    var pm = new plateMap(1, 'sample');
    pm.printID();
    setTimeout(function() {
      assert.equal($('.content').html(), '<p>Plate #1: Fecal Plate #1</p>');
      done();
    });
  });

  QUnit.test('plateMap.printID', function(assert) {
    var x = 'hi there';
    assert.equal(x, 'hi there');
  });

});
